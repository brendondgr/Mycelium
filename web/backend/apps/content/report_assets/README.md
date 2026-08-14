# Daily report cover assets

The two images on the daily report's cover, checked in because the backend has
to render a PDF wherever it runs — a container that cannot reach the repo's art
pipeline still has to produce a report with a cover on it.

Both are **derivatives**. Edit the master in `web/art/`, never these; the
renderer treats a missing or unreadable file as "no cover art" and lays the
cover out without it (see `daily_report_pdf._cover_marks`).

| File | Master | How it was made |
| --- | --- | --- |
| `mylo-headshot.png` | `web/art/Mylo/MyloHeadshot-e1.png` | alpha-trimmed, scaled to 400px tall |
| `mycelium-logo.png` | `web/art/logo/logo-colored.svg` | `rsvg-convert -w 700`, scaled to 400px tall |

Both are 400px tall so they sit as a matched pair at the same height on the
cover, and are drawn at roughly an inch — around 400 dpi, which is why they need
no more resolution than this.

To regenerate after a master changes:

```bash
rsvg-convert -w 700 web/art/logo/logo-colored.svg -o /tmp/logo.png
uv run --project web/backend python - <<'PY'
from PIL import Image

OUT, H = "web/backend/apps/content/report_assets", 400


def fit(path, dest, *, trim=True):
    im = Image.open(path).convert("RGBA")
    if trim and (box := im.getchannel("A").getbbox()):
        im = im.crop(box)
    im.resize((round(im.width * H / im.height), H), Image.LANCZOS).save(
        dest, optimize=True
    )


fit("web/art/Mylo/MyloHeadshot-e1.png", f"{OUT}/mylo-headshot.png")
fit("/tmp/logo.png", f"{OUT}/mycelium-logo.png")
PY
```
