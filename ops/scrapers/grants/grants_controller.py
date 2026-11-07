"""Run a small grants source sampling ingest and write normalized CSV files."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from normalizers import grants_gov as grants_gov_normalizer
from normalizers import nih_reporter as nih_reporter_normalizer
from normalizers import nsf_awards as nsf_awards_normalizer
from retrievers import grants_gov, nih_reporter, nsf_awards
from writers.csv_writer import write_grants_csv

MIN_LIMIT = 5
MAX_LIMIT = 10
DEFAULT_LIMIT = 10
DEFAULT_OUTPUT_DIR = Path("data/grants")
ALL_SOURCES = ("grants_gov", "nih_reporter", "nsf_awards")


@dataclass(frozen=True)
class SourceConfig:
    """The functions and output file for one grant source."""

    name: str
    output_filename: str
    retrieve: Callable[[int], list[dict]]
    normalize: Callable[[list[dict]], list[dict[str, str]]]


SOURCE_CONFIGS = {
    "grants_gov": SourceConfig(
        name="grants_gov",
        output_filename="grants_gov_sample.csv",
        retrieve=grants_gov.retrieve,
        normalize=grants_gov_normalizer.normalize_records,
    ),
    "nih_reporter": SourceConfig(
        name="nih_reporter",
        output_filename="nih_reporter_sample.csv",
        retrieve=nih_reporter.retrieve,
        normalize=nih_reporter_normalizer.normalize_records,
    ),
    "nsf_awards": SourceConfig(
        name="nsf_awards",
        output_filename="nsf_awards_sample.csv",
        retrieve=nsf_awards.retrieve,
        normalize=nsf_awards_normalizer.normalize_records,
    ),
}


def parse_sources(raw_sources: str) -> list[str]:
    sources = [source.strip() for source in raw_sources.split(",") if source.strip()]
    invalid_sources = [source for source in sources if source not in SOURCE_CONFIGS]
    if invalid_sources:
        valid = ", ".join(ALL_SOURCES)
        invalid = ", ".join(invalid_sources)
        raise argparse.ArgumentTypeError(f"unknown source(s): {invalid}. Valid: {valid}")
    if not sources:
        raise argparse.ArgumentTypeError("at least one source is required")
    return sources


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch small grant samples from public sources and write CSVs."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"records per source, clamped to {MIN_LIMIT}-{MAX_LIMIT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for generated CSV files",
    )
    parser.add_argument(
        "--sources",
        type=parse_sources,
        default=list(ALL_SOURCES),
        help="comma-separated list: grants_gov,nih_reporter,nsf_awards",
    )
    return parser.parse_args()


def clamp_limit(limit: int) -> tuple[int, str | None]:
    if limit < MIN_LIMIT:
        return MIN_LIMIT, f"requested limit {limit} raised to minimum {MIN_LIMIT}"
    if limit > MAX_LIMIT:
        return MAX_LIMIT, f"requested limit {limit} lowered to maximum {MAX_LIMIT}"
    return limit, None


def run_source(config: SourceConfig, limit: int, output_dir: Path) -> bool:
    output_path = output_dir / config.output_filename
    warnings: list[str] = []

    try:
        raw_records = config.retrieve(limit)
    except Exception as exc:  # noqa: BLE001 - source failures are non-fatal here.
        print(f"{config.name}: warning: retrieval failed: {exc}", file=sys.stderr)
        return False

    if not raw_records:
        warnings.append("source returned zero records")

    normalized_records = config.normalize(raw_records)
    write_grants_csv(output_path, normalized_records)

    warning_text = f" warnings={'; '.join(warnings)}" if warnings else ""
    print(
        f"{config.name}: requested={limit} retrieved={len(raw_records)} "
        f"csv={output_path}{warning_text}"
    )
    return True


def main() -> int:
    args = parse_args()
    limit, limit_warning = clamp_limit(args.limit)
    if limit_warning:
        print(f"warning: {limit_warning}", file=sys.stderr)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    successes = 0
    for source_name in args.sources:
        config = SOURCE_CONFIGS[source_name]
        if run_source(config, limit, output_dir):
            successes += 1

    if successes == 0:
        print("all selected grant sources failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
