"""H5 of EXP-2026-09-009: the collaborator search panel in a real browser.

Runs on the host against a web server proxying to a backend on the sandbox
database (never the development one — see PROTOCOL.md for how both are
started). Signs in as the sandbox seeker ``browser-prep`` prepared, then at
desktop and phone width: opens the panel from a grant card, runs it, opens it
from the project's Collaborators tab, and from the Cmd-K palette. Each step is
a DOM assertion and a screenshot; the result is one JSON object.

    uv run python docs/research/experiments/EXP-2026-09-009-*/code/browser_check.py \
        --base http://localhost:18002 --username p0000 --password ... \
        --project <uuid> --out data/sandbox-browser/exp009
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

VIEWPORTS = {"desktop": (1280, 800), "phone": (390, 844)}


def no_page_scroll(page: Page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth + 1"
    )


def sign_in(page: Page, base: str, username: str, password: str) -> None:
    page.goto(f"{base}/login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/app/**", timeout=60_000)


def panel(page: Page):
    return page.get_by_role("dialog", name="Find collaborators")


def check(page: Page, base: str, project: str, shots: Path, tag: str) -> dict:
    out: dict = {}

    # 1. A grant card whose team fit has a gap offers the search.
    page.goto(f"{base}/app/grants")
    button = page.get_by_role("button", name="Find collaborators").first
    button.wait_for(timeout=90_000)
    out["grants_no_page_scroll"] = no_page_scroll(page)
    button.scroll_into_view_if_needed()
    page.screenshot(path=shots / f"{tag}-1-grant-card.png")
    button.click()
    dialog = panel(page)
    expect(dialog).to_be_visible()
    chips = dialog.get_by_role("list", name="Requirements").get_by_role("listitem")
    expect(chips.first).to_be_visible(timeout=30_000)
    out["call_chips"] = chips.count()
    out["call_chips_marked_gap"] = dialog.get_by_role("listitem").filter(
        has_text="gap"
    ).count()
    out["panel_no_page_scroll"] = no_page_scroll(page)
    page.screenshot(path=shots / f"{tag}-2-panel-prefilled.png")

    # 2. Run: two groups, never merged; or the honest empty state.
    dialog.get_by_role("button", name="Run").click()
    outcome = dialog.locator("section h3, p:has-text('who is open to collaboration')")
    outcome.first.wait_for(timeout=180_000)
    headings = dialog.locator("section h3").all_inner_texts()
    out["result_groups"] = headings
    out["empty_state"] = dialog.get_by_text("who is open to collaboration").count() > 0
    out["evidence_tags"] = dialog.get_by_text("from their papers").count() + (
        dialog.get_by_text("from their profile").count()
    )
    out["hits_shown"] = dialog.locator("section li").count()
    page.screenshot(path=shots / f"{tag}-3-results.png", full_page=False)
    dialog.locator("div.flex-1").first.evaluate("el => el.scrollTo(0, 99999)")
    page.screenshot(path=shots / f"{tag}-3b-results-scrolled.png")
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()

    # 3. The project's Collaborators tab.
    page.goto(f"{base}/app/projects/{project}")
    page.get_by_role("tab", name="Collaborators").click()
    page.get_by_role("button", name="Find collaborators").click()
    dialog = panel(page)
    chips = dialog.get_by_role("list", name="Requirements").get_by_role("listitem")
    expect(chips.first).to_be_visible(timeout=60_000)
    out["project_chips"] = chips.count()
    out["project_no_page_scroll"] = no_page_scroll(page)
    page.screenshot(path=shots / f"{tag}-4-project-panel.png")
    page.keyboard.press("Escape")

    # 4. The Cmd-K palette, with the typed words carried into the panel.
    page.locator("body").click(position={"x": 5, "y": 5})
    page.keyboard.press("Control+k")
    palette = page.get_by_role("dialog", name="Switch workspace")
    palette.get_by_label("Jump to a workspace").fill("kriging for reef temperature")
    palette.get_by_role("button", name="Find collaborators").click()
    dialog = panel(page)
    expect(dialog).to_be_visible()
    out["palette_text_carried"] = (
        dialog.locator("#collab-need").input_value() == "kriging for reef temperature"
    )
    page.screenshot(path=shots / f"{tag}-5-palette-panel.png")
    page.keyboard.press("Escape")
    return out


def _to_api(api: str):
    def handler(route):
        url = route.request.url
        route.fulfill(response=route.fetch(url=api + url[url.index("/api/") :]))

    return handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--api",
        help="Send /api/ straight to this backend (as nginx does in the real "
        "stack); the Next dev server alone loops on trailing slashes.",
    )
    args = parser.parse_args()
    shots = Path(args.out)
    shots.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for tag, (width, height) in VIEWPORTS.items():
            context = browser.new_context(viewport={"width": width, "height": height})
            if args.api:
                context.route("**/api/**", _to_api(args.api.rstrip("/")))
            page = context.new_page()
            errors: list[str] = []
            page.on(
                "console",
                lambda m, errors=errors: errors.append(m.text)
                if m.type == "error"
                else None,
            )
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            sign_in(page, args.base, args.username, args.password)
            try:
                report[tag] = check(page, args.base, args.project, shots, tag)
            except Exception as exc:  # recorded, not hidden
                page.screenshot(path=shots / f"{tag}-failure.png")
                report[tag] = {"error": f"{type(exc).__name__}: {exc}"}
            report[tag]["console_errors"] = errors
            context.close()
        browser.close()
    failures = []
    for tag, result in report.items():
        if "error" in result:
            failures.append(f"{tag}: {result['error']}")
            continue
        for key in (
            "grants_no_page_scroll",
            "panel_no_page_scroll",
            "project_no_page_scroll",
            "palette_text_carried",
        ):
            if not result.get(key):
                failures.append(f"{tag}.{key}")
        if result["call_chips"] < 1 or result["call_chips_marked_gap"] < 1:
            failures.append(f"{tag}.call_chips")
        if result["project_chips"] < 1:
            failures.append(f"{tag}.project_chips")
        if not result["empty_state"] and not result["result_groups"]:
            failures.append(f"{tag}.no_outcome")
        if result["hits_shown"] and result["evidence_tags"] < result["hits_shown"]:
            failures.append(f"{tag}.evidence_tags")
        if result["console_errors"]:
            failures.append(f"{tag}.console_errors")
    report["invariant_failures"] = failures
    text = json.dumps(report, indent=1, sort_keys=True)
    (shots / "browser.json").write_text(text)
    print(text)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
