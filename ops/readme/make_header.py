"""Generate the README banner from the project logo.

Reads  web/art/logo/logo-colored.svg   (the one copy of the drawing)
Writes docs/assets/header.svg          (committed; the README shows it)

Run from the repository root:  python3 ops/readme/make_header.py

GitHub will not render an SVG referenced inside another SVG, so the banner
embeds the logo's paths. Re-run this whenever the logo, the README's opening
sentence, or the stack changes. Everything you would normally edit is in the
block at the top. The colours are the public site's Night Forest palette
(web/landing/src/styles/global.css).
"""

import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "web/art/logo/logo-colored.svg"
OUT = ROOT / "docs/assets/header.svg"

TITLE = "Mycelium"
TAGLINE = (  # keep in step with the README's first sentence
    "An open-source academic research assistant",
    "that any lab can run on its own computers.",
)
LANGUAGES = [  # dot colours are GitHub's own (github/linguist)
    ("Python", "#3572a5"),
    ("TypeScript", "#3178c6"),
    ("Astro", "#ff5a03"),
    ("CSS", "#663399"),
]
STACK = [(n, None) for n in ("Django", "Next.js", "Postgres + pgvector", "Docker Compose")]

PANEL_BG, PANEL_EDGE = "#10140e", "#26301f"
CHIP_BG, CHIP_EDGE = "#161c13", "#334029"
TEXT, CHIP_TEXT, MUTED = "#f3ead6", "#cdd5c0", "#9aa68b"
THREAD, SPORE = "#b8d99a", "#e7d8b8"  # the site's sage glow and accent-soft

SANS = "ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"

W = 1000
MARK, MARK_CY = 150.0, 112.0  # logo's longest side, and its centre from the top
TITLE_Y, TITLE_SIZE = 254, 64
TAGLINE_Y, TAGLINE_SIZE, LINE_H = 292, 19, 27
ROWS_Y, ROW_H = 352, 44
CHIP_H, CHIP_FS, CHIP_GAP, CHIP_PAD = 32, 14.0, 10.0, 15.0
DOT_R, DOT_GUTTER, ADVANCE = 4.0, 13.0, 0.6

rows = [r for r in (LANGUAGES, STACK) if r]
H = int(ROWS_Y + ROW_H * (len(rows) - 1) + CHIP_H + 30)


def logo():
    raw = LOGO.read_text()
    raw = re.sub(r"<metadata>.*?</metadata>", "", raw, flags=re.S)
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    head = raw[raw.index("<svg") : raw.index(">", raw.index("<svg"))]
    _, _, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', head).group(1).split())
    body = raw[raw.index(">", raw.index("<svg")) + 1 : raw.rindex("</svg>")].strip()
    return body, w, h


def threads():
    """Faint mycelium threads rising from the bottom corners, seeded so every run matches."""
    rng = random.Random(7)
    parts = []
    for side in (-1, 1):
        for _ in range(5):
            x0 = W / 2 + side * rng.uniform(330, 490)
            y0 = H + 4
            x1 = x0 - side * rng.uniform(30, 120)
            y1 = H - rng.uniform(90, 220)
            cx_, cy_ = (x0 + x1) / 2 + side * rng.uniform(-40, 40), (y0 + y1) / 2
            parts.append(
                f'<path d="M{x0:.0f},{y0:.0f} Q{cx_:.0f},{cy_:.0f} {x1:.0f},{y1:.0f}" '
                f'fill="none" stroke="{THREAD}" stroke-width="1.2" stroke-opacity="0.18" '
                f'stroke-linecap="round" />'
            )
            parts.append(f'<circle cx="{x1:.0f}" cy="{y1:.0f}" r="2.2" fill="{THREAD}" fill-opacity="0.35" />')
    for _ in range(26):
        x = rng.uniform(24, W - 24)
        y = rng.uniform(20, H - 20)
        if abs(x - W / 2) < 300 and y > 40:  # keep the centre column clean
            continue
        parts.append(
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.uniform(0.8, 2.0):.1f}" '
            f'fill="{SPORE}" fill-opacity="{rng.uniform(0.15, 0.4):.2f}" />'
        )
    return "\n  ".join(parts)


def chip_row(items, y):
    widths = [
        CHIP_PAD * 2 + len(label) * CHIP_FS * ADVANCE + (DOT_GUTTER if dot else 0.0)
        for label, dot in items
    ]
    x = (W - (sum(widths) + CHIP_GAP * (len(items) - 1))) / 2
    parts = []
    for (label, dot), width in zip(items, widths):
        text_x = x + CHIP_PAD
        parts.append(
            f'<rect x="{x:.1f}" y="{y:g}" width="{width:.1f}" height="{CHIP_H}" '
            f'rx="{CHIP_H / 2:g}" fill="{CHIP_BG}" stroke="{CHIP_EDGE}" />'
        )
        if dot:
            parts.append(
                f'<circle cx="{text_x + DOT_R:.1f}" cy="{y + CHIP_H / 2:.1f}" r="{DOT_R:g}" fill="{dot}" />'
            )
            text_x += DOT_GUTTER
        parts.append(
            f'<text x="{text_x:.1f}" y="{y + CHIP_H / 2 + 5:.1f}" font-family="{MONO}" '
            f'font-size="{CHIP_FS:g}" fill="{CHIP_TEXT}">{label.replace("+", "&#43;")}</text>'
        )
        x += width + CHIP_GAP
    return "\n  ".join(parts)


body, lw, lh = logo()
scale = MARK / max(lw, lh)
cx = W / 2
lx, ly = cx - lw * scale / 2, MARK_CY - lh * scale / 2
taglines = "\n  ".join(
    f'<text x="{cx:g}" y="{TAGLINE_Y + i * LINE_H:g}" text-anchor="middle" '
    f'font-family="{SANS}" font-size="{TAGLINE_SIZE}" fill="{MUTED}">{line}</text>'
    for i, line in enumerate(TAGLINE)
)
chips = "\n  ".join(chip_row(row, ROWS_Y + i * ROW_H) for i, row in enumerate(rows))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" \
width="{W}" height="{H}" role="img" aria-label="{TITLE}: {' '.join(TAGLINE)}">
  <!-- Generated by ops/readme/make_header.py from web/art/logo/logo-colored.svg. Edit that, not this. -->
  <defs>
    <clipPath id="panel"><rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="24" /></clipPath>
    <radialGradient id="glow" cx="50%" cy="22%" r="45%">
      <stop offset="0" stop-color="{THREAD}" stop-opacity="0.16" />
      <stop offset="1" stop-color="{THREAD}" stop-opacity="0" />
    </radialGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="24" fill="{PANEL_BG}" />
  <g clip-path="url(#panel)">
    <rect width="{W}" height="{H}" fill="url(#glow)" />
    {threads()}
  </g>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="24" fill="none" stroke="{PANEL_EDGE}" />
  <g transform="translate({lx:.1f},{ly:.1f}) scale({scale:.6f})">
    {body}
  </g>
  <text x="{cx:g}" y="{TITLE_Y}" text-anchor="middle" font-family="{SANS}" \
font-size="{TITLE_SIZE}" font-weight="700" letter-spacing="-1" fill="{TEXT}">{TITLE}</text>
  {taglines}
  {chips}
</svg>
""")
print(f"wrote {OUT.relative_to(ROOT)}")
