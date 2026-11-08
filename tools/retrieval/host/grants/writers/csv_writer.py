"""CSV writer for normalized grant sample rows."""

from __future__ import annotations

import csv
from pathlib import Path

from normalizers.common import FIELDNAMES


def write_grants_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
