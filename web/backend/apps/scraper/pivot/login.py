"""Interactive Pivot-RP login — vendored from the ProQuest tool's ``login.py``.

Run this once (and again whenever your session expires). It opens a real
Chromium window. Log in by hand — including your institution's SSO button and
any MFA/2FA. When you can see the Pivot funding pages, come back to this
terminal and press ENTER. Your authenticated session is then saved to
``STATE_PATH`` (``storage_state.json``), which the scraper reuses so you
never have to share a password or re-do SSO for every run.

``playwright`` is an optional extra — this module imports cleanly when it is
absent; the import happens inside :func:`login`.
"""

from __future__ import annotations

from .common import CONTEXT_KWARGS, LAUNCH_ARGS, LOGIN_URL, STATE_PATH


def login() -> None:
    """Open a browser, wait for the human to complete SSO, and save the session.

    Saves Playwright storage state (cookies + localStorage) to
    :data:`~apps.scraper.pivot.common.STATE_PATH` for reuse by the scrapers.
    """
    from playwright.sync_api import sync_playwright  # lazy

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=LAUNCH_ARGS)
        context = browser.new_context(**CONTEXT_KWARGS)
        page = context.new_page()

        print("Opening Pivot-RP login page in a browser window...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        print("\n" + "=" * 70)
        print("  LOG IN NOW in the browser window that just opened.")
        print("  - Click 'Use login from my institution' and complete SSO/MFA")
        print("  - Wait until you land on the Pivot funding pages")
        print("  - Then return HERE and press ENTER")
        print("=" * 70 + "\n")

        try:
            input("Press ENTER once you are fully logged in... ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted — no session saved.")
            browser.close()
            return

        current = page.url
        if "session/login" in current:
            print(f"\n[!] The active tab is still on the login page ({current}).")
            ans = input("    Save anyway? [y/N] ").strip().lower()
            if ans != "y":
                print("Not saving. Re-run when you're logged in.")
                browser.close()
                return

        context.storage_state(path=str(STATE_PATH))
        print(f"\n[ok] Session saved to {STATE_PATH}")
        print("     You can close the browser. Next: run the scraper.")
        browser.close()
