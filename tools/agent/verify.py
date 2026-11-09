"""The citation check, run on a final answer before the turn ends.

Every ``#n`` the answer cites must be a reference this thread surfaced (a
tagged object or something a function returned). The same idea as
``tools/delivery/weekly_verify.py``: deterministic code checks the model's
claims against what it was actually shown. One repair is asked for; if that
fails too, the unmatched citations are removed and the person is told.
"""

from __future__ import annotations

import re

from . import refs

_CITE = re.compile(r"#(\d+)\b")


def cited(text: str) -> list[int]:
    return sorted({int(n) for n in _CITE.findall(text or "")})


def unmatched(thread, text: str) -> list[int]:
    known = {e["n"] for e in refs.thread_refs(thread)}
    return [n for n in cited(text) if n not in known]


def repair_message(missing: list[int]) -> str:
    listed = ", ".join(f"#{n}" for n in missing)
    return (
        f"These citations do not match anything you were shown in this "
        f"conversation: {listed}. Answer again, citing only reference numbers "
        "you were given, or none."
    )


def strip(text: str, missing: list[int]) -> str:
    bad = {str(n) for n in missing}
    out = _CITE.sub(lambda m: "" if m.group(1) in bad else m.group(0), text)
    return re.sub(r"[ \t]+([,.;:)])", r"\1", re.sub(r"\(\s*\)", "", out)).strip()
