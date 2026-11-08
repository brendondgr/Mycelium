"""The nightly run's container stages, assembled from the loaded tools.

``ops/nightly/manual_all.py`` used to hold the stage list by hand. Now each tool
declares its stages (``Tool.stages``) with a phase, and this module orders them:
by phase (:data:`tools._framework.spec.PHASES`), then platform stages before
tool stages, then tools in dependency order, then each tool's declaration
order — adjusted only by explicit ``after`` constraints inside a phase.

Order is the product rule (collect, rank the whole corpus, take each target's
slate, remind before pruning, brief from what the day settled) and a golden
test holds the assembled plan to the one the hand-written list produced.

Standard library only: the host-side runner imports it without Django.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from . import discovery, loader
from .spec import PHASES, Stage, Tool

#: Stages the platform itself owns. Every stage today belongs to a tool; a
#: platform-owned stage would be declared here.
PLATFORM_STAGES: tuple[Stage, ...] = ()


@dataclass(frozen=True)
class Planned:
    stage: Stage
    owner: str  # "platform" or a tool name


class PlanError(ValueError):
    pass


def order_stages(
    tools: Iterable[type[Tool]], platform: Iterable[Stage] = PLATFORM_STAGES
) -> list[Planned]:
    """``tools`` must already be in dependency order."""
    buckets: dict[str, list[Planned]] = {phase: [] for phase in PHASES}
    for stage in platform:
        buckets[stage.phase].append(Planned(stage, "platform"))
    for cls in tools:
        for stage in cls.stages:
            buckets[stage.phase].append(Planned(stage, cls.name))
    seen_commands: set[str] = set()
    out: list[Planned] = []
    for phase in PHASES:
        items = buckets[phase]
        commands = [p.stage.command for p in items]
        for p in items:
            if p.stage.command in seen_commands:
                raise PlanError(f"stage {p.stage.command} is declared twice")
            seen_commands.add(p.stage.command)
        out.extend(_apply_after(items, set(commands)))
    return out


def _apply_after(items: list[Planned], in_phase: set[str]) -> list[Planned]:
    """Stable topological order honouring ``after`` within one phase."""
    remaining = list(items)
    placed: list[Planned] = []
    done: set[str] = set()
    while remaining:
        for i, item in enumerate(remaining):
            needs = [a for a in item.stage.after if a in in_phase and a not in done]
            if not needs:
                placed.append(item)
                done.add(item.stage.command)
                del remaining[i]
                break
        else:
            raise PlanError(
                "stage ordering cycle among: "
                + ", ".join(p.stage.command for p in remaining)
            )
    return placed


def plan_for(
    loaded: Iterable[str] | None = None,
) -> tuple[list[Planned], list[Planned]]:
    """``(to run, skipped)`` for the given loaded tool names.

    ``loaded=None`` plans as if every readable installed tool were loaded —
    the static view the golden test and ``--plan`` use when the container
    cannot be asked.
    """
    found = discovery.discover()
    deps = {n: tuple(d.cls.depends_on) if d.cls else () for n, d in found.items()}
    order, _cyclic = loader.dependency_order(deps)
    classes = [found[n].cls for n in order if found[n].cls is not None]
    everything = order_stages(classes)
    if loaded is None:
        return everything, []
    loaded = set(loaded)
    run = [p for p in everything if p.owner == "platform" or p.owner in loaded]
    skipped = [p for p in everything if p not in run]
    return run, skipped


def as_tuples(planned: Iterable[Planned]) -> list[tuple[str, list[str], str]]:
    """The ``(command, args, intro)`` shape ``manual_all.py`` runs."""
    return [(p.stage.command, list(p.stage.args), p.stage.intro) for p in planned]
