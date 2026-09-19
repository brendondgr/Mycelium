"""EXP-2026-09-016: ambient Plans 07-08 in a real browser, with keyboard and
axe-core checks.

Runs on the host against a web server proxying to a backend on the sandbox
database ``mycelium_sandbox_ambweb`` (see PROTOCOL.md; ``code/prep.py`` made
the data). The phone pass is read-only and runs first; the desktop pass makes
the changes. Each check is a DOM assertion; axe-core is scoped to
``[data-ambient]`` regions. The result is one JSON object.

    uv run python .../code/browser_check.py --base http://localhost:18002 \
        --api http://localhost:18001 --username amb_b3_cyra --password x \
        --prep .../data/prep.json --out data/sandbox-browser/exp016
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[5]
AXE = ROOT / "web" / "node_modules" / "axe-core" / "axe.min.js"
VIEWPORTS = {"phone": (390, 844), "desktop": (1280, 800)}
TABS = ["Needs your answer", "What changed", "Faded and declined", "What Mylo knows", "Settings"]


def no_page_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def axe(page: Page) -> dict:
    """Serious/critical and other violations inside ``[data-ambient]``."""
    if not page.locator("[data-ambient]").count():
        return {"regions": 0, "serious": [], "other": []}
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
          const r = await axe.run({include: [["[data-ambient]"]]},
            {runOnly: {type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]}});
          return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,
            nodes: v.nodes.map(n => n.target.join(" ")).slice(0, 5)}));
        }"""
    )
    return {
        "regions": page.locator("[data-ambient]").count(),
        "serious": [v for v in result if v["impact"] in ("serious", "critical")],
        "other": [v for v in result if v["impact"] not in ("serious", "critical")],
    }


def keyboard_sweep(page: Page, start, region: str, limit: int = 120) -> dict:
    """Tab from ``start`` and record every button reached inside ``region``,
    and whether its focus is visible (outline or shadow differs from blurred)."""
    buttons = page.evaluate(
        f"""() => [...document.querySelectorAll('{region} button:not([disabled]),'
                + '{region} summary, {region} select, {region} a[href], {region} input')]
            .filter(el => el.offsetParent !== null).length"""
    )
    start.focus()
    reached, invisible = set(), []
    for _ in range(limit):
        page.keyboard.press("Tab")
        info = page.evaluate(
            f"""() => {{
              const el = document.activeElement;
              if (!el || !el.closest('{region}')) return null;
              const tag = el.tagName.toLowerCase();
              if (!['button','summary','select','a','input'].includes(tag)) return {{skip: true}};
              const id0 = (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 60)
                + '#' + [...document.querySelectorAll('{region} *')].indexOf(el);
              // A date input's segments each take a Tab; blurring and refocusing
              // it restarts them, so its focus ring is not compared (run 3).
              if (tag === 'input') return {{id: id0, visible: true}};
              const f = getComputedStyle(el);
              const focused = [f.outlineStyle, f.outlineWidth, f.boxShadow].join('|');
              const id = (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 60)
                + '#' + [...document.querySelectorAll('{region} *')].indexOf(el);
              el.blur();
              const b = getComputedStyle(el);
              const blurred = [b.outlineStyle, b.outlineWidth, b.boxShadow].join('|');
              el.focus({{focusVisible: true}});
              // getComputedStyle is live: compare the strings captured before
              // and after blur, never the objects (fixed after run 2).
              return {{id, visible: focused !== blurred}};
            }}"""
        )
        if info is None:
            if reached:
                break
            continue
        if info.get("skip"):
            continue
        reached.add(info["id"])
        if not info["visible"]:
            invisible.append(info["id"])
    return {"controls": buttons, "reached": len(reached), "focus_invisible": invisible}


def sign_in(page: Page, base: str, username: str, password: str) -> None:
    page.goto(f"{base}/login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/app/**", timeout=90_000)


def open_tab(page: Page, name: str) -> None:
    page.get_by_role("tab", name=re.compile(rf"^{re.escape(name)}")).click()
    page.wait_for_timeout(400)


def mylo(page: Page, base: str) -> None:
    page.goto(f"{base}/app/mylo-and-you")
    expect(page.get_by_role("heading", name="Mylo & you")).to_be_visible(timeout=90_000)


def repeated_names(page: Page, region: str) -> dict:
    """Buttons in a region whose accessible names repeat (e.g. five "Undo")."""
    names = page.evaluate(
        f"""() => [...document.querySelectorAll('{region} button')]
            .filter(b => b.offsetParent !== null)
            .map(b => (b.getAttribute('aria-label') || b.textContent || '').trim())"""
    )
    counts: dict[str, int] = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    return {n: c for n, c in counts.items() if c > 1}


def survey(page: Page, base: str, prep: dict, shots: Path, tag: str) -> dict:
    """Read-only: every ambient surface, its axe result and page scroll."""
    out: dict = {"pages": {}}
    mylo(page, base)
    for name in TABS:
        open_tab(page, name)
        key = f"mylo:{name}"
        out["pages"][key] = {"no_page_scroll": no_page_scroll(page), "axe": axe(page)}
        page.screenshot(path=shots / f"{tag}-mylo-{name.split()[0].lower()}.png", full_page=True)
        if name == "Needs your answer":
            sizes = page.evaluate(
                """() => [...document.querySelectorAll('[role=group][aria-label^="Answer about"] button')]
                    .map(b => { const r = b.getBoundingClientRect(); return [r.width, r.height]; })"""
            )
            out["answer_buttons"] = len(sizes)
            out["answer_buttons_under_24px"] = sum(1 for w, h in sizes if w < 24 or h < 24)
        if name == "What changed":
            out["repeated_names_changed"] = repeated_names(page, "#mylo-panel")
        if name == "What Mylo knows":
            out["repeated_names_knows"] = repeated_names(page, "#mylo-panel")
    others = {
        "profile": "/app/profile",
        "project": f"/app/projects/{prep['project_id']}",
        "lab": f"/app/overview?ws={prep['lab_slug']}",
        "account": "/app/account",
    }
    for key, path in others.items():
        page.goto(f"{base}{path}")
        page.wait_for_load_state("networkidle", timeout=90_000)
        page.wait_for_timeout(1500)
        out["pages"][key] = {
            "no_page_scroll": no_page_scroll(page),
            "axe": axe(page),
            "ambient_regions": page.evaluate(
                "() => [...document.querySelectorAll('[data-ambient]')].map(e => e.dataset.ambient)"
            ),
        }
        page.screenshot(path=shots / f"{tag}-{key}.png", full_page=True)
    return out


def flows(page: Page, base: str, prep: dict, shots: Path) -> dict:
    """Desktop only: the changes, in the order a person would make them."""
    out: dict = {}

    # Profile: the "heard" mark from the applied yes.
    page.goto(f"{base}/app/profile")
    page.wait_for_load_state("networkidle", timeout=90_000)
    page.wait_for_timeout(1500)
    heard = page.locator("[data-ambient=provenance]")
    out["heard_before"] = heard.count()
    out["heard_sr_text"] = heard.first.inner_text() if heard.count() else ""

    # Needs your answer: the tabs pattern, then answer one by button.
    mylo(page, base)
    first = page.get_by_role("tab", name=re.compile(r"^Needs your answer\s*\d"))
    first.wait_for(timeout=60_000)  # the badge loads after the tab (run 2)
    badge_before = first.inner_text()
    first = page.get_by_role("tab", name=re.compile("^Needs your answer"))
    first.focus()
    page.keyboard.press("ArrowRight")
    out["arrow_moves_selection"] = (
        page.get_by_role("tab", name="What changed").get_attribute("aria-selected") == "true"
    )
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("Tab")
    out["tab_enters_panel"] = page.evaluate("document.activeElement?.id") == "mylo-panel"
    open_tab(page, "Needs your answer")
    out["keyboard_answer"] = keyboard_sweep(
        page, page.get_by_role("tab", name=re.compile("^Needs your answer")), "#mylo-panel"
    )
    groups = page.locator('[role=group][aria-label^="Answer about"]')
    out["questions_shown"] = groups.count()
    group = groups.first
    later = group.get_by_role("button", name=re.compile("not now|later", re.I))
    (later.first if later.count() else group.get_by_role("button").first).click()
    status = page.get_by_role("status").first
    expect(status).to_be_visible(timeout=30_000)
    out["answer_reply"] = status.inner_text()
    page.wait_for_timeout(1500)
    out["badge_before"] = badge_before
    out["badge_after"] = first.inner_text()
    page.screenshot(path=shots / "desktop-flow-1-answered.png", full_page=True)

    # What changed: Undo the profile edit; the history keeps it.
    open_tab(page, "What changed")
    out["keyboard_changed"] = keyboard_sweep(
        page, page.get_by_role("tab", name="What changed"), "#mylo-panel"
    )
    rows = page.locator("#mylo-panel li")
    out["changes_listed"] = rows.count()
    out["undo_buttons"] = page.locator("#mylo-panel").get_by_role("button", name=re.compile("^Undo")).count()
    edit = rows.filter(has_text="Profile edited").first
    out["profile_edit_row"] = edit.count() > 0
    if edit.count():
        edit.get_by_role("button", name=re.compile("^Undo")).click()
        page.wait_for_timeout(2500)
        out["undone_rows"] = page.locator("#mylo-panel li").filter(has_text=re.compile("Undone|undone")).count()
    page.screenshot(path=shots / "desktop-flow-2-undone.png", full_page=True)
    page.goto(f"{base}/app/profile")
    page.wait_for_load_state("networkidle", timeout=90_000)
    page.wait_for_timeout(1500)
    out["heard_after_undo"] = page.locator("[data-ambient=provenance]").count()

    # What Mylo knows: four sections.
    mylo(page, base)
    open_tab(page, "What Mylo knows")
    out["knows_sections"] = page.locator("#mylo-panel section[aria-label]").count()

    # Settings: two named switches; questions off and back on.
    open_tab(page, "Settings")
    switches = page.get_by_role("switch")
    out["switches"] = switches.count()
    questions = page.get_by_role("switch", name="Mylo's questions")
    was = questions.get_attribute("aria-checked")
    questions.click()
    expect(questions).to_have_attribute("aria-checked", "false" if was == "true" else "true", timeout=15_000)
    questions = page.get_by_role("switch", name="Mylo's questions")
    questions.click()
    expect(questions).to_have_attribute("aria-checked", was, timeout=15_000)
    out["questions_switch_round_trip"] = True
    out["keyboard_settings"] = keyboard_sweep(
        page, page.get_by_role("tab", name="Settings"), "#mylo-panel"
    )

    # Project: the conversation proposal, accepted.
    page.goto(f"{base}/app/projects/{prep['project_id']}")
    card = page.locator("[data-ambient=reflection]")
    card.wait_for(timeout=90_000)
    heard_item = card.locator("li").filter(has_text="Heard in conversation").first
    out["proposal_marked_heard"] = heard_item.count() > 0
    out["proposal_text"] = heard_item.inner_text() if heard_item.count() else ""
    out["project_developments_card"] = page.locator("[data-ambient=project-developments]").count()
    page.screenshot(path=shots / "desktop-flow-3-proposal.png", full_page=True)
    if heard_item.count():
        heard_item.get_by_role("button", name="Accept").click()
        page.wait_for_timeout(2500)
    mylo(page, base)
    open_tab(page, "What changed")
    out["state_edit_row"] = page.locator("#mylo-panel li").filter(has_text="Project state edited").count()

    # The bell: an ambient notification opens Mylo & you in the same tab.
    page.goto(f"{base}/app/overview")
    page.get_by_role("button", name=re.compile("^Notifications")).click()
    dialog = page.get_by_role("dialog", name="Notifications")
    expect(dialog).to_be_visible()
    link = dialog.locator('a[href="/app/mylo-and-you"]').first
    try:
        link.wait_for(timeout=30_000)  # the list loads after the dialog (run 2)
    except Exception:  # noqa: BLE001 - counted as zero below
        pass
    out["bell_ambient_links"] = dialog.locator('a[href="/app/mylo-and-you"]').count()
    out["bell_link_same_tab"] = link.get_attribute("target") is None if out["bell_ambient_links"] else False
    if out["bell_ambient_links"]:
        link.click()
        page.wait_for_url("**/app/mylo-and-you", timeout=30_000)
        out["bell_opened_mylo"] = True
    return out


def _to_api(api: str):
    def handler(route):
        url = route.request.url
        route.fulfill(response=route.fetch(url=api + url[url.index("/api/") :]))

    return handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--api")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--prep", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    prep = json.loads(Path(args.prep).read_text())
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
            page.set_default_timeout(60_000)
            errors: list[str] = []
            page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            sign_in(page, args.base, args.username, args.password)
            result: dict = {}
            try:
                result["survey"] = survey(page, args.base, prep, shots, tag)
                if tag == "desktop":
                    result["flows"] = flows(page, args.base, prep, shots)
            except Exception as exc:  # recorded, not hidden
                page.screenshot(path=shots / f"{tag}-failure.png", full_page=True)
                result["error"] = f"{type(exc).__name__}: {exc}"
            result["console_errors"] = errors
            report[tag] = result
            context.close()
        browser.close()
    report["failures"] = failures(report)
    text = json.dumps(report, indent=1, sort_keys=True)
    (shots / "browser.json").write_text(text)
    print(text)
    return 1 if report["failures"] else 0


def failures(report: dict) -> list[str]:
    out = []
    for tag in VIEWPORTS:
        result = report.get(tag, {})
        if "error" in result:
            out.append(f"{tag}: {result['error']}")
        for key, page in result.get("survey", {}).get("pages", {}).items():
            if not page["no_page_scroll"]:
                out.append(f"{tag}.{key}.page_scroll")
            for v in page["axe"]["serious"]:
                out.append(f"{tag}.{key}.axe.{v['id']}")
        if result.get("survey", {}).get("answer_buttons_under_24px"):
            out.append(f"{tag}.answer_buttons_under_24px")
        if result.get("console_errors"):
            out.append(f"{tag}.console_errors")
    f = report.get("desktop", {}).get("flows", {})
    if f:
        checks = {
            "heard_before": f.get("heard_before", 0) >= 1,
            "arrow_moves_selection": f.get("arrow_moves_selection"),
            "tab_enters_panel": f.get("tab_enters_panel"),
            "questions_shown": f.get("questions_shown", 0) >= 1,
            "answer_reply": bool(f.get("answer_reply")),
            "badge_moved": f.get("badge_before") != f.get("badge_after"),
            "undo_buttons": f.get("undo_buttons", 0) >= 1,
            "profile_edit_undone": f.get("undone_rows", 0) >= 1,
            "heard_gone_after_undo": f.get("heard_after_undo") == f.get("heard_before", 0) - 1,
            "knows_sections": f.get("knows_sections") == 4,
            "switches": f.get("switches", 0) >= 2,
            "questions_switch_round_trip": f.get("questions_switch_round_trip"),
            "proposal_marked_heard": f.get("proposal_marked_heard"),
            "state_edit_row": f.get("state_edit_row", 0) >= 1,
            "bell_link_same_tab": f.get("bell_link_same_tab"),
            "bell_opened_mylo": f.get("bell_opened_mylo"),
        }
        out += [f"desktop.flows.{k}" for k, ok in checks.items() if not ok]
        for sweep in ("keyboard_answer", "keyboard_changed", "keyboard_settings"):
            s = f.get(sweep) or {}
            if s.get("reached", 0) < s.get("controls", 0):
                out.append(f"desktop.{sweep}.unreached({s.get('reached')}/{s.get('controls')})")
            if s.get("focus_invisible"):
                out.append(f"desktop.{sweep}.focus_invisible")
    for tag in VIEWPORTS:
        pages = report.get(tag, {}).get("survey", {}).get("pages", {})
        for key in ("profile", "project", "lab", "account"):
            want = {"project": "reflection", "lab": "lab-changes", "account": "settings", "profile": "provenance"}[key]
            if key in pages and want not in pages[key].get("ambient_regions", []):
                out.append(f"{tag}.{key}.missing_{want}")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
