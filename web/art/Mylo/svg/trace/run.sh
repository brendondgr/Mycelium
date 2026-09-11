#!/usr/bin/env bash
# Regenerate ../mylo.svg from docs/Resources/myloCharacterCard.png.
# Needs: python3 with Pillow + numpy, and potrace on PATH. ~20 s.
set -euo pipefail
cd "$(dirname "$0")"
python3 build.py 2>&1 | grep -E 'colours|paths:' 
python3 props.py 2>/dev/null
python3 assemble.py
