"""Shared constants and HTML parse helpers for the Pivot-RP scrapers.

Vendored from the ProQuest tool's ``utils/ProQuest/common.py``. The scrapers reuse
ONE authenticated session (``storage_state.json``) whose path is configurable via
the ``PIVOT_STORAGE_STATE`` env var so a deployment can mount the secret wherever
it likes without touching code.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

BASE = "https://pivot.proquest.com"
LOGIN_URL = f"{BASE}/session/login"

# Saved auth session (cookies + localStorage). Git-ignored, treated like a
# password. Location is overridable so the daily job can find it in a mounted
# secret; defaults to the package directory for local, human-paced use.
_DEFAULT_STATE = Path(__file__).resolve().parent / "storage_state.json"
STATE_PATH = Path(os.environ.get("PIVOT_STORAGE_STATE", _DEFAULT_STATE))

# Launch args that stop the browser from advertising itself as automated, which
# some institutional SSO / IdP pages block.
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# A normal desktop-Chrome-ish context so pages get a sane viewport.
CONTEXT_KWARGS = {
    "viewport": {"width": 1440, "height": 900},
    "locale": "en-US",
}


def state_exists() -> bool:
    """True when a non-empty saved session is present."""
    return STATE_PATH.exists() and STATE_PATH.stat().st_size > 0


def clean_text(text: str) -> str:
    """Collapse whitespace and drop a trailing more/less toggle word."""
    text = " ".join((text or "").split())
    text = re.sub(r"\s*\b(Show\s+)?(more|less)\s*$", "", text, flags=re.I)
    return text.strip()


def label_value_map(soup):
    """Map normalized ``span.small-label`` text -> its value-column element.

    Pivot detail pages (funding and papers-invited) lay each field out as a label
    column (``div.col-md-2 > span.small-label``) followed by a value column (the
    next sibling ``div``). Some labels are wrapped with an info icon (e.g. an AI
    summary); we keep only the trailing human label.
    """
    out = {}
    for lab in soup.select("span.small-label"):
        label = " ".join(lab.get_text(" ", strip=True).split())
        label = re.sub(r"^.*?(AI Generated (?:Title|Summary))$", r"\1", label)
        col = lab.find_parent("div")
        value = col.find_next_sibling("div") if col else None
        if label and value is not None and label not in out:
            out[label] = value
    return out
