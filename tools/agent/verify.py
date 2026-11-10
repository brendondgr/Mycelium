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


# --------------------------------------------------------------------------- #
# Grounding: what an answer says about an item must come from what was read
# --------------------------------------------------------------------------- #
#: A line that states one concrete fact about an item ("- **Authors:** …").
_FACT_LINE = re.compile(
    r"^[ \t]*(?:[-*•][ \t]+)?(?:\*\*|__)?(?P<label>authors?|venue|journal|"
    r"conference|published(?: in)?|publisher|doi|funders?|sponsors?|agency|"
    r"deadline|due|amount|award(?: amount)?|budget|location|dates?|year)"
    r"(?:\*\*|__)?[ \t]*:[ \t]*(?:\*\*|__)?[ \t]*(?P<value>.+)$",
    re.I | re.M,
)
_DOI = re.compile(r"\b10\.\d{4,9}/[^\s)\]>*`\"']+")
#: A measured figure stated in prose: 92%, 0.87, 3.5x.
_FIGURE = re.compile(r"(?<![#\w.])\d+(?:\.\d+)?\s?%|(?<![#\w.])\d+\.\d+(?![\w.])")
_NAME_SPLIT = re.compile(r",|;|\band\b|&", re.I)
_STOP = frozenset(
    "the and for with from into this that their of in on at to by an a "
    "et al university institute international journal conference".split()
)


def _fold(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.casefold())


def _clean_value(value: str) -> str:
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)  # [text](url) → text
    value = _CITE.sub("", value)
    return re.sub(r"[*_`<>]", "", value).strip(" .")


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W\d_]{3,}", text) if w not in _STOP]


def _supported(label: str, value: str, source: str) -> bool:
    label = label.casefold()
    if label == "doi":
        found = _DOI.search(value or "")
        return found is None or _fold(found.group(0).rstrip(".,;")) in source
    value = _fold(_clean_value(value))
    if not value:
        return True
    if label.startswith("author"):
        for part in _NAME_SPLIT.split(value):
            names = _words(part)
            if names and names[-1] not in source:
                return False
        return True
    numbers =re.findall(r"\d[\d,.]*", value)
    if numbers:
        return all(n.rstrip(".,") in source for n in numbers)
    words = _words(value)
    if not words:
        return True
    return sum(w in source for w in words) >= max(1, round(len(words) * 0.6))


def source_text(results: list[dict], extra: list[str] = ()) -> str:
    """Everything the answer may draw facts from, folded for matching."""
    parts = [str(p.get("content") or "") for p in results]
    parts += [str(x) for x in extra]
    return _fold("\n".join(parts))


def seen_refs(results: list[dict], extra: list[str] = ()) -> set[int]:
    """The reference numbers a lookup in view returned, or a card named."""
    seen = {int(n) for p in results for n in (p.get("refs") or [])}
    for card in extra:
        seen |= {int(n) for n in re.findall(r"^#(\d+)\b", str(card), re.M)}
    return seen


def unsupported(text: str, source: str) -> list[str]:
    """Concrete claims in ``text`` that nothing in ``source`` backs: fact
    lines (authors, venue, DOI, dates, amounts…), DOIs and measured figures.
    Returned as the exact snippets, in order, without repeats."""
    out: list[str] = []
    for m in _FACT_LINE.finditer(text or ""):
        if not _supported(m.group("label"), m.group("value"), source):
            out.append(m.group(0).strip())
    for m in _DOI.finditer(text or ""):
        doi = m.group(0).rstrip(".,;")
        if _fold(doi) not in source and not any(doi in line for line in out):
            out.append(doi)
    for m in _FIGURE.finditer(text or ""):
        figure = m.group(0).replace(" ", "")
        if figure not in source.replace(" ", "") and not any(
            m.group(0) in line for line in out
        ):
            out.append(m.group(0))
    return list(dict.fromkeys(out))


def unread(thread, text: str, seen: set[int]) -> list[int]:
    """Cited references that exist in the thread but that nothing in view
    shows: the answer leans on a title it saw earlier, not on the item."""
    known = {e["n"] for e in refs.thread_refs(thread)}
    return [n for n in cited(text) if n in known and n not in seen]


def grounding_message(unread_refs: list[int], claims: list[str]) -> str:
    parts = []
    if unread_refs:
        listed = ", ".join(f"#{n}" for n in unread_refs)
        them = "it" if len(unread_refs) == 1 else "them"
        parts.append(
            f"You cite {listed} but have not read {them} "
            "in what you can see now. Read each one with its read function "
            "(corpus_item, projects_get, …) before saying anything about it."
        )
    if claims:
        shown = "\n".join(f"- {c}" for c in claims[:8])
        parts.append(
            "These details are not in anything you read, so they may be wrong:\n"
            f"{shown}\nRead the item they are about, then answer again using only "
            "what it says. Leave out any detail you cannot find."
        )
    return "\n\n".join(parts)


def strip_claims(text: str, claims: list[str]) -> str:
    """Remove unbacked fact lines and figures after a failed repair."""
    out = text
    for claim in claims:
        if _FACT_LINE.fullmatch(claim):
            out = re.sub(rf"^[ \t]*{re.escape(claim)}[ \t]*\n?", "", out, flags=re.M)
        else:
            # A DOI or a figure inside prose: drop its whole sentence, so no
            # half-sentence is left behind.
            out = re.sub(
                rf"[^.!?\n]*{re.escape(claim)}[^.!?\n]*[.!?]?[ \t]*", "", out
            )
    return re.sub(r"\n{3,}", "\n\n", out).strip()
