#!/usr/bin/env bash
# Regenerate ../mylo.svg from web/art/Mylo/myloCharacterCard.png.
# Needs python3 with Pillow + numpy. About 3 s.
set -euo pipefail
cd "$(dirname "$0")"
python3 draw.py
