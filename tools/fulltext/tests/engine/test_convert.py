"""Payload conversion, including the pypdf path that replaced pymupdf4llm."""

from xml.etree import ElementTree as ET

from tools.fulltext.engine.convert import (
    bytes_to_markdown,
    elsevier_to_markdown,
    html_to_markdown,
    jats_to_markdown,
    pdf_to_markdown,
)

SENTENCE = "Polystyrene nanoparticles crossed the blood brain barrier in mice."


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal valid PDF with one Helvetica text line per entry."""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for lines in pages:
        ops = ["BT", "/F1 10 Tf", "14 TL", "50 780 Td"]
        for line in lines:
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({esc}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        content = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content} 0 R >>"
        )
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return out


def test_pdf_converts_with_pypdf_reflowing_lines_and_cutting_references():
    body = (
        ["Introduction", ""]
        + [SENTENCE] * 12
        + [""]
        + [
            "Exposure was measured with pyrolysis gas chromatography and the counts",
            "were normalised to tissue mass across every animal in the cohort.",
        ]
        * 4
    )
    refs = ["References", "1. Someone et al. A paper. 2020."]
    pdf = make_pdf([body, body + refs])
    md = pdf_to_markdown(pdf, min_chars=200)
    assert SENTENCE in md
    # Two printed lines of one sentence come back as one paragraph line.
    assert "counts were normalised to tissue mass" in md
    assert "Someone et al" not in md  # the reference list is dropped


def test_short_or_broken_pdfs_are_not_full_text():
    assert pdf_to_markdown(make_pdf([["Too short."]]), min_chars=500) == ""
    assert pdf_to_markdown(b"%PDF-1.4 not really a pdf", min_chars=10) == ""


def test_bytes_router_sends_pdfs_to_pypdf():
    md, kind = bytes_to_markdown(
        make_pdf([[SENTENCE] * 20]), "application/octet-stream", 100
    )
    assert kind == "pdf" and SENTENCE in md


def test_jats_keeps_sections_captions_and_drops_back_matter():
    xml = f"""<article><body>
      <sec><title>Results</title><p>{SENTENCE * 10}</p>
        <fig><label>Figure 1</label><caption><p>Uptake over time.</p></caption></fig>
      </sec>
      <sec><title>Acknowledgements</title><p>Thanks to everyone.</p></sec>
    </body></article>"""
    md = jats_to_markdown(ET.fromstring(xml), min_chars=100)
    assert md.startswith("### Results")
    assert "*Figure 1 Uptake over time.*" in md
    assert "Thanks to everyone" not in md


def test_elsevier_xml_renders_its_body():
    xml = f"""<full-text-retrieval-response xmlns:ce="http://www.elsevier.com/xml/common/dtd"
        xmlns:xocs="http://www.elsevier.com/xml/xocs/dtd">
      <originalText><xocs:doc><body><ce:sections><ce:section>
        <ce:section-title>Methods</ce:section-title><ce:para>{SENTENCE * 10}</ce:para>
      </ce:section></ce:sections></body></xocs:doc></originalText>
    </full-text-retrieval-response>"""
    md = elsevier_to_markdown(xml, min_chars=100)
    assert md.startswith("### Methods") and SENTENCE in md


def test_html_landing_page_is_not_full_text_but_a_pdf_link_is_followed():
    landing = (
        "<html><body><article><h1>Title</h1><p>Short abstract.</p>"
        "</article></body></html>"
    )
    assert html_to_markdown(landing) == ""
    linked = (
        '<html><head><meta name="citation_pdf_url" content="https://x/a.pdf"></head>'
        "<body>abstract</body></html>"
    )
    assert html_to_markdown(linked) == ("pdf", "https://x/a.pdf")
    md, kind = bytes_to_markdown(linked.encode(), "text/html", 500)
    assert md == "" and kind == ("pdf-link", "https://x/a.pdf")
