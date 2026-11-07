"""Capture the README screenshots from the public site.

Writes docs/assets/screenshot-{hero,report,feeds}.webp (committed).

Needs a running landing dev server (the `landing` entry in .claude/launch.json,
or `npm --prefix web/landing run dev -- --port 4322`), Playwright's Chromium
(`uv run playwright install chromium`), and ImageMagick's `magick` for the
crop and WebP encode. Run from the repository root:

    uv run ops/readme/screenshots.py [--url http://localhost:4322/]

The shots show the landing page's sample content for a fictional lab, never
real user data. Re-run it when the front page changes.
"""

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/assets"
HIDE_TOOLBAR = "astro-dev-toolbar{display:none!important}"
HIDE_HEADER = "header.site-header{visibility:hidden!important}"
# name, selector (None = the viewport), crop as WxH+X+Y (None = as captured)
SHOTS = [
    ("hero", None, None),
    ("report", "#report", "1280x680+0+90"),
    ("feeds", "section.feeds-sec", "1280x740+0+100"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:4322/")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 760}, color_scheme="dark")
        page.goto(args.url, wait_until="networkidle")
        page.add_style_tag(content=HIDE_TOOLBAR)
        time.sleep(3.5)  # let the hero's threads and reveals finish
        for name, selector, crop in SHOTS:
            raw = Path(tmp) / f"{name}.png"
            if selector is None:
                page.screenshot(path=raw)
            else:
                page.add_style_tag(content=HIDE_HEADER)
                page.locator(selector).scroll_into_view_if_needed()
                time.sleep(2.5)
                page.locator(selector).screenshot(path=raw)
            cmd = ["magick", str(raw)]
            if crop:
                cmd += ["-crop", crop, "+repage"]
            dest = OUT / f"screenshot-{name}.webp"
            subprocess.run([*cmd, "-quality", "90", "-define", "webp:method=6", str(dest)], check=True)
            print(f"wrote {dest.relative_to(ROOT)}")
        browser.close()


if __name__ == "__main__":
    main()
