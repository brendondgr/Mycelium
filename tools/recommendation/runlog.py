"""A small timestamped run log for the daily pipeline.

Each :meth:`RunLog.line` is written with a UTC millisecond timestamp to a per-run
file (and optionally echoed to a stream, e.g. the management command's stdout), so
a reader can follow what the daily search did — how many papers each source
returned for each query, the de-duplication tally, and how long every phase took.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


class RunLog:
    """Append timestamped lines to a file and/or an echo callback."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        echo: Callable[[str], None] | None = None,
    ) -> None:
        self.path = path
        self.echo = echo
        self._fh = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("a", encoding="utf-8")

    def line(self, message: str) -> None:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        text = f"[{stamp}] {message}"
        if self._fh is not None:
            self._fh.write(text + "\n")
            self._fh.flush()
        if self.echo is not None:
            self.echo(text)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> RunLog:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def new_run_log(
    directory: str | Path,
    *,
    label: str = "run",
    echo: Callable[[str], None] | None = None,
) -> RunLog:
    """Open a fresh timestamp-named log file under ``directory``."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return RunLog(Path(directory) / f"{stamp}-{label}.log", echo=echo)
