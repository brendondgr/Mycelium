"""Beat's scheduler: the schedule in memory, plus a heartbeat file.

Celery's default ``PersistentScheduler`` keeps its state in a ``shelve`` file,
which on Python 3.13 is SQLite (``dbm.sqlite3``). Beat stalled twice while that
file's write-ahead log sat at several megabytes (2026-08-04 and 2026-11-14), and
since the container now starts every Beat from an empty schedule, the file
bought nothing. This scheduler keeps the schedule in memory and touches
``HEARTBEAT`` on every tick; the healthcheck in ``compose.yaml`` reads that
file's age to tell a working Beat from a wedged one.
"""

from __future__ import annotations

import os
from pathlib import Path

from celery.beat import Scheduler

HEARTBEAT = Path(os.environ.get("BEAT_HEARTBEAT", "/tmp/beat-heartbeat"))


class HeartbeatScheduler(Scheduler):
    def tick(self, *args, **kwargs):
        try:
            HEARTBEAT.touch()
        except OSError:  # the heartbeat is advisory; never stop scheduling
            pass
        return super().tick(*args, **kwargs)
