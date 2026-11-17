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


#: The kinds whose name is short and exact enough to be recognised in prose.
_NAMED_KINDS = ("person", "project")
_HANDLE = re.compile(r"\s*\(@[^)]*\)$")


def number_names(thread, text: str, seen: set[int]) -> tuple[str, list[int]]:
    """Give its reference number to each person or project the answer names
    without one, and return the numbers added.

    An answer named the right people and gave no number (C-043: "**Jonah
    Whitcombe** (@demo.jonah)"), so the name was not a citation and could not
    be opened. Only a reference in view (``seen``) is numbered, by its exact
    name, at its first mention, and only when no other reference of the
    thread carries that name."""
    if not text:
        return text, []
    entries = [e for e in refs.thread_refs(thread) if e.get("kind") in _NAMED_KINDS]
    names: dict[str, list[dict]] = {}
    for entry in entries:
        name = _HANDLE.sub("", str(entry.get("title") or "")).strip()
        names.setdefault(name, []).append(entry)
    already = set(cited(text))
    added = []
    for name, same in names.items():
        entry = same[0]
        n = entry["n"]
        if len(same) > 1 or len(name) < 4 or n in already or n not in seen:
            continue
        found = re.search(
            rf"(?<![\w#@]){re.escape(name)}(?![\w])(?:\*\*|__|\*|_)*", text
        )
        if found is None:
            continue
        text = f"{text[: found.end()]} (#{n}){text[found.end() :]}"
        added.append(n)
    return text, sorted(added)


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
#: A measured figure stated in prose: 92%, 0.87, €2.5M (the scale is read
#: by ``_figure_backed``, not matched).
_FIGURE = re.compile(
    r"(?<![#\w.])\d+(?:\.\d+)?\s?%"
    r"|(?<![#\w.])\d+\.\d+"
    r"(?=\s?(?:k|m|mn|b|bn|thousand|million|billion)\b|(?![\w.]))",
    re.I,
)
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


#: Labels whose value is a date: its numbers are the fact, its words a format.
_DATE_LABELS = ("deadline", "due", "date", "year", "published")
#: Labels whose value is money: numbers, read through ``_numbers_backed``.
_MONEY_LABELS = ("amount", "award", "budget")
#: "1.5M", "15 million", "€3k": the scale a written number stands for.
_SCALE = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}
_NUMBER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
    r"(?:\s?(?P<scale>k|m|mn|b|bn|thousand|million|billion)\b)?",
    re.I,
)
_RANGE_SCALE = re.compile(
    r"^\s?[–—-]\s?[€$£]?\s?\d[\d,]*(?:\.\d+)?\s?"
    r"(k|m|mn|b|bn|thousand|million|billion)\b",
    re.I,
)


def _source_numbers(source: str) -> set[float]:
    """Every number in the evidence, as written and at its stated scale:
    "€1,500,000" gives 1500000; "€1.5 million" gives 1.5 and 1500000."""
    out: set[float] = set()
    # Links and DOIs are identifiers, not amounts: "10.1145/3770855.3818893"
    # once backed an invented "$3.8 million" (EXP-2026-11-013 Amendment 4).
    source = _DOI.sub(" ", re.sub(r"\bhttps?://\S+|\bwww\.\S+", " ", source))
    for m in _NUMBER.finditer(source):
        value = float(m.group(1).replace(",", "") + "." + (m.group(2) or "0"))
        out.add(value)
        if m.group("scale"):
            out.add(value * _SCALE[m.group("scale").casefold()])
    return out


def _same_number(value: float, numbers: set[float], tolerance: float = 0.0) -> bool:
    slack = max(tolerance, 1e-9)
    return any(abs(value - n) <= slack * max(1.0, abs(n)) if not tolerance
               else abs(value - n) <= tolerance for n in numbers)


def _rounding(written: str, scale: float) -> float:
    """Half a unit of the last written digit, at scale: "8.9" millions is
    ±50,000, so "€8.9M" stands for "€8,925,000" (EXP-2026-11-013 Amendment 4)."""
    decimals = len(written.split(".", 1)[1]) if "." in written else 0
    return 0.5 * 10 ** (-decimals) * scale


def _figure_backed(text: str, m: re.Match, numbers: set[float]) -> bool:
    """A prose figure the evidence states in another form: "€1.5–15M" for
    "€1,500,000–€15,000,000" (EXP-2026-11-013: two of three repairs removed a
    correct amount over its formatting). Percentages are left to the literal
    check: 0.87 and 87% are not interchangeable claims."""
    raw = m.group(0).replace(" ", "")
    if raw.endswith("%"):
        return False
    value = float(raw)
    after = text[m.end():]
    scale = re.match(r"\s?(k|m|mn|b|bn|thousand|million|billion)\b", after, re.I)
    if scale is None:
        scale = _RANGE_SCALE.match(after)  # the scale after a range's end
    if _same_number(value, numbers):
        return True
    if scale is None:
        return False
    factor = _SCALE[scale.group(1).casefold()]
    return _same_number(value * factor, numbers, _rounding(raw, factor))


def _numbers_backed(value: str, source: str, *, money: bool = False) -> bool:
    found = re.findall(r"\d[\d,.]*", value)
    if not money:
        return all(n.rstrip(".,") in source for n in found)
    numbers = _source_numbers(source)
    for m in _NUMBER.finditer(value):
        n = m.group(1) + (f".{m.group(2)}" if m.group(2) else "")
        if n in source:
            continue
        written = float(m.group(1).replace(",", "") + "." + (m.group(2) or "0"))
        if _same_number(written, numbers):
            continue
        if not m.group("scale"):
            return False
        factor = _SCALE[m.group("scale").casefold()]
        slack = _rounding(n.replace(",", ""), factor)
        if not _same_number(written * factor, numbers, slack):
            return False
    return True


def _supported(label: str, value: str, source: str) -> bool:
    label = label.casefold()
    if label == "doi":
        found = _DOI.search(value or "")
        return found is None or _fold(found.group(0).rstrip(".,;")) in source
    value = _fold(_clean_value(value))
    if not value:
        return True
    if label.startswith("author"):
        # A year or count written beside the names is checked too
        # ("Cheon and Kakinuma (2024)" passed when the item said 2026).
        if not _numbers_backed(value, source):
            return False
        for part in _NAME_SPLIT.split(re.sub(r"\(?\d[\d,.]*\)?", " ", value)):
            names = _words(part)
            if names and names[-1] not in source:
                return False
        return True
    if label.startswith(_MONEY_LABELS):
        return _numbers_backed(value, source, money=True)
    if not _numbers_backed(value, source):
        return False
    if label.startswith(_DATE_LABELS) and label != "published in":
        return True
    # A venue, funder, publisher or place: every distinctive word must be in
    # the evidence. Three in five was enough before, and an invented
    # "Marine Forecasting Letters" passed on "marine" and "forecasting".
    words = _words(value)
    return all(w in source for w in words)


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
    numbers = None
    for m in _FIGURE.finditer(text or ""):
        figure = m.group(0).replace(" ", "")
        if figure in source.replace(" ", "") or any(m.group(0) in line for line in out):
            continue
        if numbers is None:
            numbers = _source_numbers(source)
        if not _figure_backed(text, m, numbers):
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
            "what it says. Leave out any detail you cannot find. Write the answer "
            "as if for the first time: the person never saw your draft, so do not "
            "mention a correction, a draft or this check."
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
