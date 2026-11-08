"""The recommendation write door: running the ranking and registering what it
should rank for.

The nightly runs (papers, then opportunities), on-demand refits after a
sign-up or a profile edit, project seeding, and the extension point through
which code built on recommendation asks for extra targets to be scored.
"""

from tools.recommendation.opportunities import run_daily_opportunities_batch
from tools.recommendation.pipeline import run_daily_batch
from tools.recommendation.refitting import (
    refit_batch,
    refit_lab,
    refit_project,
    refit_target,
    refit_targets_batch,
    refit_user,
)
from tools.recommendation.tasks import (
    enqueue_project_seed,
    register_department_source,
    select_departments,
    select_targets,
    select_users,
)

__all__ = [
    "enqueue_project_seed",
    "refit_batch",
    "refit_lab",
    "refit_project",
    "refit_target",
    "refit_targets_batch",
    "refit_user",
    "register_department_source",
    "run_daily_batch",
    "run_daily_opportunities_batch",
    "select_departments",
    "select_targets",
    "select_users",
]
