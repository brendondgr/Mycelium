"""The last daily-run outcome, shared between the run and the bot.

``manual_all.py`` writes this file at the end of each run; the Mylo bot's
``/mylo lastrun`` command reads it. Keeping the path and shape in one module
means the writer and reader can never drift apart. Stdlib only, so both the bare
root runner and the bot can import it.
"""

from __future__ import annotations

import json
import socket
from datetime import datetime
from pathlib import Path

#: ``data/logs/`` at the repository root (one level up from this package).
RUN_STATE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "logs" / "mylo-last-run.json"
)


def write_run_state(
    *,
    ok: bool,
    scrape_ran: bool,
    stages_run: list[str],
    failed_stage: str | None = None,
    exit_code: int = 0,
) -> None:
    """Persist the run outcome. Best-effort — a write failure never raises."""
    state = {
        "finished_at": datetime.now().astimezone().isoformat(),
        "host": socket.gethostname(),
        "ok": ok,
        "scrape_ran": scrape_ran,
        "stages_run": stages_run,
        "failed_stage": failed_stage,
        "exit_code": exit_code,
    }
    try:
        RUN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUN_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def read_run_state() -> dict | None:
    """Return the last run's state, or ``None`` if it has never run / is unreadable."""
    try:
        return json.loads(RUN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
