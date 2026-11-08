"""Provider payloads -> markdown: JATS XML, Elsevier XML, PDF, HTML, plain text.

Section headings are kept, figure and table captions become italics, and
reference lists and back matter are dropped. Every converter returns ``""``
when what it was given is too short to be an article body, so a landing page
or a front-matter stub never counts as full text.

PDFs convert with ``pypdf`` (BSD) — not PubMedExtraction's ``pymupdf4llm``,
which is AGPL-3.0 and cannot ship in an Apache-2.0 project. ``pypdf`` gives
plain text without layout headings; the original PDF is always kept, and most
full text arrives as XML anyway.
"""

from __future__ import annotations

import io
import logging
import re
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Back-matter and float sections that add noise rather than content.
SKIP_SEC_TYPES = {
    "supplementary-material",
    "COI-statement",
    "conflict",
    "funding",
    "data-availability",
}
SKIP_TITLES = re.compile(
    r"^(references?|bibliography|acknowledge?ments?|conflicts? of interest|"
    r"competing interests?|author contributions?|funding|supplementary|"
    r"data availability|abbreviations)\b",
    re.I,
)
REFS_HEADING = re.compile(
    r"^\s{0,3}(#{1,6}\s*|\*\*)?\s*(references?|bibliography|literature cited|"
    r"works cited)\s*(\*\*)?\s*$",
    re.I | re.M,
)
HTML_MIN_CHARS = 5000  # a publisher page below this is a landing page, not an article
TEXT_MIN_CHARS = 3000


# --------------------------------------------------------------------------- #
# JATS (PMC / Europe PMC / Springer)
# --------------------------------------------------------------------------- #
def local_name(tag) -> str:
    """Local name of a possibly namespaced tag."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(node) -> str:
    """Flattened inline text of an element, with whitespace collapsed."""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def _render_sec(sec, depth, out):
    title_el = sec.find("title")
    title = _text(title_el) if title_el is not None else ""
    if SKIP_TITLES.match(title) or sec.get("sec-type", "") in SKIP_SEC_TYPES:
        return
    if title:
        out.append(f"{'#' * min(depth, 6)} {title}")
        out.append("")
    for child in sec:
        if child is title_el:
            continue
        _render_node(child, depth + 1, out)


def _render_node(node, depth, out):
    tag = node.tag
    if tag == "sec":
        _render_sec(node, depth, out)
    elif tag == "p":
        txt = _text(node)
        if txt:
            out.append(txt)
            out.append("")
    elif tag in ("fig", "table-wrap"):
        cap = node.find("caption")
        label = _text(node.find("label")) if node.find("label") is not None else ""
        if cap is not None:
            body = _text(cap)
            if body:
                out.append(f"*{label + ' ' if label else ''}{body}*")
                out.append("")
    elif tag == "list":
        for item in node.findall("list-item"):
            txt = _text(item)
            if txt:
                out.append(f"- {txt}")
        out.append("")
    elif tag in ("boxed-text", "statement", "disp-quote"):
        txt = _text(node)
        if txt:
            out.append(f"> {txt}")
            out.append("")


def strip_ns(root):
    """Drop namespaces in place so JATS from any provider renders the same way."""
    for el in root.iter():
        if isinstance(el.tag, str):
            el.tag = local_name(el.tag)
    return root


def jats_to_markdown(article, min_chars: int = 500) -> str:
    """Render an <article>'s <body> as markdown. '' when there is none."""
    body = article.find("body")
    if body is None:
        body = next((el for el in article.iter() if local_name(el.tag) == "body"), None)
        if body is None:
            return ""
        strip_ns(article)
    out: list[str] = []
    for child in body:
        _render_node(child, 3, out)  # body sections start at h3
    md = "\n".join(out).strip()
    return md if len(md) >= min_chars else ""


def article_ids(article) -> tuple[str, str]:
    """(pmcid, pmid) as recorded inside a PMC <article>."""
    pmcid = pmid = ""
    for aid in article.iter("article-id"):
        kind, value = aid.get("pub-id-type"), (aid.text or "").strip()
        if kind in ("pmcid", "pmc") and not pmcid:
            pmcid = value if value.startswith("PMC") else f"PMC{value}"
        elif kind == "pmid" and not pmid:
            pmid = value
    return pmcid, pmid


# --------------------------------------------------------------------------- #
# Elsevier full-text XML
# --------------------------------------------------------------------------- #
def _els_render(node, depth, out):
    name = local_name(node.tag)
    if name == "section":
        title = next((c for c in node if local_name(c.tag) == "section-title"), None)
        if title is not None:
            t = _text(title)
            if SKIP_TITLES.match(t):
                return
            if t:
                out.append(f"{'#' * min(depth, 6)} {t}")
                out.append("")
        for child in node:
            if child is not title:
                _els_render(child, depth + 1, out)
    elif name in ("para", "simple-para", "note-para"):
        txt = _text(node)
        if txt:
            out.append(txt)
            out.append("")
    elif name in ("figure", "table"):
        cap = next((c for c in node if local_name(c.tag) == "caption"), None)
        lab = next((c for c in node if local_name(c.tag) == "label"), None)
        if cap is not None:
            body = _text(cap)
            if body:
                prefix = (_text(lab) + " ") if lab is not None else ""
                out.append(f"*{prefix}{body}*")
                out.append("")
    elif name == "list":
        for item in node:
            if local_name(item.tag) == "list-item":
                txt = _text(item)
                if txt:
                    out.append(f"- {txt}")
        out.append("")
    elif name in (
        "bibliography",
        "acknowledgment",
        "further-reading",
        "index",
        "glossary",
        "appendices",
        "label",
        "section-title",
        "cross-ref",
    ):
        return
    else:
        for child in node:
            _els_render(child, depth, out)


def elsevier_to_markdown(xml_text: str, min_chars: int = 500) -> str:
    """A ScienceDirect Article Retrieval response as markdown ('' if no body)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    # Structured body: <xocs:doc> ... <ja:body> <ce:sections> ... nested inside
    # <originalText>, either as elements or as escaped text.
    original = next(
        (el for el in root.iter() if local_name(el.tag) == "originalText"), None
    )
    doc = original
    if (
        original is not None
        and not len(original)
        and (original.text or "").lstrip().startswith("<")
    ):
        try:
            doc = ET.fromstring(original.text)
        except ET.ParseError:
            doc = None
    if doc is not None:
        body = next((el for el in doc.iter() if local_name(el.tag) == "body"), None)
        if body is not None:
            out: list[str] = []
            for child in body:
                _els_render(child, 3, out)
            md = "\n".join(out).strip()
            if len(md) >= min_chars:
                return md
        raw = next((el for el in doc.iter() if local_name(el.tag) == "rawtext"), None)
        if raw is not None:
            txt = (raw.text or "").strip()
            if len(txt) >= max(min_chars, TEXT_MIN_CHARS):
                return text_to_markdown(txt)
    return ""


# --------------------------------------------------------------------------- #
# PDF / HTML / plain text
# --------------------------------------------------------------------------- #
def cut_references(md: str) -> str:
    """Drop everything from the last 'References' heading on, if it sits past
    40% of the document."""
    hits = list(REFS_HEADING.finditer(md))
    if hits and hits[-1].start() > len(md) * 0.4:
        return md[: hits[-1].start()].rstrip()
    return md


def _reflow_page(text: str) -> str:
    """Join pypdf's hard-wrapped lines into paragraphs.

    pypdf ends every printed line with a newline. A line-end hyphen before a
    lowercase letter is a broken word. A short capitalised line with no closing
    punctuation is a heading and stands alone. A line well short of the page's
    width (the last line of a paragraph) closes the paragraph, and so does a
    sentence end on a line that is not full; anything else continues it.
    """
    text = re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)
    lines = [ln.strip() for ln in text.splitlines()]
    paras: list[str] = []
    cur: list[str] = []
    # A full line's length: the 80th percentile, so one overlong line (a URL,
    # a running header) does not make every ordinary line look short.
    lengths = sorted(len(ln) for ln in lines if ln)
    width = lengths[int(len(lengths) * 0.8)] if lengths else 0
    for ln in lines:
        if not ln:
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        short = len(ln) < width * 0.6
        if short and ln[:1].isupper() and not ln.endswith((".", ",", ";")):
            # A heading ("Methods", "References") stands alone.
            if cur:
                paras.append(" ".join(cur))
                cur = []
            paras.append(ln)
            continue
        cur.append(ln)
        if short or (ln.endswith((".", "?", "!", ":")) and len(ln) < width * 0.8):
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(p for p in paras if p)


def pdf_to_markdown(data: bytes, min_chars: int = 500) -> str:
    """PDF bytes -> plain-paragraph markdown with ``pypdf``. '' for an
    unreadable, encrypted or image-only PDF."""
    from pypdf import PdfReader

    pypdf_log = logging.getLogger("pypdf")
    level = pypdf_log.level
    pypdf_log.setLevel(logging.ERROR)  # malformed-but-readable PDFs warn on every page
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # any failure means unreadable
                return ""
        pages = [_reflow_page(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # corrupt PDFs raise many kinds
        log.info("pdf conversion failed: %s", exc)
        return ""
    finally:
        pypdf_log.setLevel(level)
    md = cut_references("\n\n".join(p for p in pages if p)).strip()
    return md if len(md) >= min_chars else ""


def text_to_markdown(txt: str) -> str:
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", txt)]
    return cut_references("\n\n".join(p for p in paras if p))


def html_to_markdown(html: str, min_chars: int = HTML_MIN_CHARS):
    """A publisher or repository page -> markdown, or ``("pdf", url)`` when the
    page advertises a PDF instead. Landing pages that only carry an abstract
    fail the length test and count as no full text."""
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", attrs={"name": re.compile(r"^citation_pdf_url$", re.I)})
    if meta and meta.get("content"):
        return ("pdf", meta["content"])
    for tag in soup(
        ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]
    ):
        tag.decompose()
    candidates = soup.find_all(["article", "main"]) or [soup.body or soup]
    node = max(candidates, key=lambda n: len(n.get_text(" ", strip=True)))
    out: list[str] = []
    for el in node.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not txt:
            continue
        if el.name[0] == "h":
            out.append(f"{'#' * min(int(el.name[1]) + 2, 6)} {txt}")
        elif el.name == "li":
            out.append(f"- {txt}")
        else:
            out.append(txt)
        out.append("")
    md = cut_references("\n".join(out).strip())
    return md if len(md) >= min_chars else ""


def bytes_to_markdown(data: bytes, content_type: str | None, min_chars: int):
    """Route a downloaded payload to the right converter.

    Returns ``(md, kind)`` where kind is 'pdf' / 'jats' / 'html' / 'text' /
    'unknown', or ``("", ("pdf-link", url))`` when an HTML page points at a PDF.
    """
    ct = (content_type or "").lower()
    head = data[:2048].lstrip()
    if head.startswith(b"%PDF") or "application/pdf" in ct:
        return pdf_to_markdown(data, min_chars), "pdf"
    text = data.decode("utf-8", errors="replace")
    if (
        head.startswith(b"<")
        and (b"<article" in data[:20000] or "xml" in ct)
        and b"<html" not in head.lower()
    ):
        try:
            root = ET.fromstring(text)
            art = (
                root
                if local_name(root.tag) == "article"
                else next(
                    (el for el in root.iter() if local_name(el.tag) == "article"), None
                )
            )
            if art is not None:
                return jats_to_markdown(strip_ns(art), min_chars), "jats"
        except ET.ParseError:
            pass
    if head.startswith(b"<") or "html" in ct:
        res = html_to_markdown(text, max(min_chars, HTML_MIN_CHARS))
        if isinstance(res, tuple):
            return "", ("pdf-link", res[1])
        return res, "html"
    if "text/plain" in ct:
        md = text_to_markdown(text)
        return (md if len(md) >= max(min_chars, TEXT_MIN_CHARS) else ""), "text"
    return "", "unknown"
