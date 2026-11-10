"""Build, inspect or remove the public demo's world.

    manage.py demo build            # (re)build from apps/demo/world.yaml, then rank it
    manage.py demo build --no-rank  # build only; the nightly run ranks it
    manage.py demo refresh          # tonight's run for the demo world, now
    manage.py demo status           # what the world holds, and whether it is current
    manage.py demo delete

The world is ordinary rows — a department, a lab inside it, its people and
projects — so the nightly run ranks and briefs it and the app shows it like
anyone's (only while ``demo.enabled`` is on: off, the run leaves it out).
``refresh`` runs that same work for the demo world alone: a literature search on
its watch topics, the paper and opportunity ranking, and each daily report.
Every person's address is under ``@showcase.mycelium.invalid`` (RFC 2606: it
can never deliver), every password is unusable (nobody signs in as them), and
``build`` always clears the previous world first, so it is safe to re-run after
editing the fixture. Whether ``/demo`` is served is a separate switch:
``demo.enabled`` in ``mycelium.toml``.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.interests import validate_interests
from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
    LabWatchPreference,
    Profile,
    WatchPreference,
)
from apps.billing.services import (
    activate_department_subscription,
    activate_lab_subscription,
    attach_lab_to_department,
    create_department_workspace,
    create_lab_workspace,
)
from apps.research.models import Project, ProjectMember

from ... import world as demo_world
from ...models import DemoQuestion, DemoWorld

FIXTURE = Path(__file__).resolve().parents[2] / "world.yaml"


def _interests(entry: dict, *, extra: dict | None = None) -> dict:
    clusters = entry.get("clusters") or []
    areas = [a for c in clusters for a in c["areas"]] or list(entry.get("areas") or [])
    payload = {
        "version": 2,
        "statement": " ".join(str(entry.get("statement", "")).split()),
        "areas": areas,
        "keywords": list(entry.get("keywords") or []),
        **({"clusters": clusters} if clusters else {}),
        **(extra or {}),
    }
    return validate_interests(payload)


class Command(BaseCommand):
    help = "Build, show or delete the public demo's fictional lab (apps/demo)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("action", choices=("build", "refresh", "status", "delete"))
        parser.add_argument(
            "--no-rank",
            action="store_true",
            help="Skip the on-demand ranking after building (the nightly run does it).",
        )
        parser.add_argument(
            "--fixture", default=str(FIXTURE), help="World file (default: world.yaml)."
        )

    def handle(self, *args, **options) -> None:
        action = options["action"]
        if action == "status":
            return self._status()
        if action == "refresh":
            built = DemoWorld.objects.select_related("lab", "department").first()
            if built is None:
                raise CommandError("No demo world. Run `manage.py demo build`.")
            self._refresh(built)
            return self._status()
        if action == "delete":
            with transaction.atomic():
                removed = self._clear()
            demo_world.forget()
            self.stdout.write(
                self.style.SUCCESS(f"Deleted the demo world ({removed}).")
            )
            return
        spec = self._load(Path(options["fixture"]))
        with transaction.atomic():
            self._clear()
            built = self._build(spec)
        demo_world.forget()
        self.stdout.write(
            self.style.SUCCESS(
                f"Built the demo: {built.lab.name} ({built.lab.slug}), viewing as "
                f"{built.viewer.get_full_name()}."
            )
        )
        if not options["no_rank"]:
            self._rank(built)
        from django.conf import settings

        if not settings.DEMO_ENABLED:
            self.stdout.write(
                "  /demo is still off. Turn it on with "
                "`ops/mycelium config set demo.enabled true`."
            )

    # -- reading -----------------------------------------------------------

    def _load(self, path: Path) -> dict:
        try:
            spec = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise CommandError(f"Cannot read {path}: {exc}") from None
        keys = {p["key"] for p in spec.get("people", [])}
        for need in (spec["lab"]["pi"], spec["department"]["chair"]):
            if need not in keys:
                raise CommandError(f"world.yaml names {need!r}, who is not in people.")
        return spec

    # -- teardown ----------------------------------------------------------

    def _clear(self) -> str:
        """Remove the previous world and only it: by the ``DemoWorld`` row, then
        anything still carrying the demo domain (a half-built earlier run)."""
        current = DemoWorld.objects.select_related("lab", "department").first()
        labs = depts = 0
        if current is not None:
            if current.department_id:
                depts += (
                    Department.objects.filter(pk=current.department_id).delete()[0]
                    and 1
                )
            labs += Lab.objects.filter(pk=current.lab_id).delete()[0] and 1
        people = User.objects.filter(email__iendswith="@" + demo_world.DOMAIN)
        # A department's owner is protected: drop the demo people's departments first.
        Department.objects.filter(owner__in=people).delete()
        Lab.objects.filter(
            memberships__user__in=people, memberships__role="owner"
        ).delete()
        DemoWorld.objects.all().delete()
        DemoQuestion.objects.all().delete()
        count, _ = people.delete()
        return f"{labs} lab, {depts} department, {count} rows of people"

    # -- building ----------------------------------------------------------

    def _person(self, entry: dict, institution: str) -> User:
        username = f"demo.{entry['key']}"
        user = User(
            username=username,
            email=f"{entry['key']}@{demo_world.DOMAIN}",
            first_name=entry["first"],
            last_name=entry["last"],
            is_active=True,
        )
        user.set_unusable_password()
        user.save()  # the post_save signal makes the Profile
        extra = {}
        if entry.get("funding_needs"):
            extra["funding_needs"] = list(entry["funding_needs"])
        if entry.get("seeking"):
            extra["seeking"] = list(entry["seeking"])
        if entry.get("stage"):
            extra["eligibility"] = {"stage": entry["stage"], "citizenship": ""}
        Profile.objects.filter(user=user).update(
            academic_title=entry["title"],
            # Not derived from the address (which places nobody): the demo's
            # institution is as fictional as its people.
            institution=institution,
            interests=_interests(entry, extra=extra),
            is_verified=True,
        )
        # Watch topics are the nightly's literature searches; without them the
        # run does not see the person at all.
        WatchPreference.objects.update_or_create(
            user=user, defaults={"topics": list(entry.get("topics") or [])}
        )
        return user

    def _build(self, spec: dict) -> DemoWorld:
        institution = spec.get("institution", "")
        people = {p["key"]: self._person(p, institution) for p in spec["people"]}
        roles = {p["key"]: p.get("lab_role") for p in spec["people"]}

        dspec = spec["department"]
        department = create_department_workspace(
            people[dspec["chair"]], dspec["name"], institution=institution
        ).department
        department.profile.statement = " ".join(dspec["statement"].split())
        department.profile.areas = list(dspec["areas"])
        department.profile.save(update_fields=["statement", "areas", "updated_at"])

        lspec = spec["lab"]
        pi = people[lspec["pi"]]
        lab = create_lab_workspace(pi, lspec["name"]).lab
        if lab.slug != lspec["slug"]:
            lab.slug = lspec["slug"]
            lab.save(update_fields=["slug", "updated_at"])
        lab_interests = _interests(lspec)
        lab.profile.statement = lab_interests["statement"]
        lab.profile.areas = lab_interests["areas"]
        lab.profile.interests = lab_interests
        lab.profile.save(
            update_fields=["statement", "areas", "interests", "updated_at"]
        )
        LabWatchPreference.objects.update_or_create(
            lab=lab, defaults={"topics": list(lspec.get("topics") or [])}
        )
        for key, user in people.items():
            role = roles.get(key)
            if user == pi or not role:
                continue
            LabMembership.objects.update_or_create(
                user=user, lab=lab, defaults={"role": role, "is_lead": False}
            )
        for key, user in people.items():
            if key == dspec["chair"]:
                continue
            DeptMembership.objects.update_or_create(
                user=user,
                department=department,
                defaults={"role": DeptMembership.Role.MEMBER},
            )

        for pspec in spec.get("projects", []):
            interests = _interests(pspec)
            project = Project.objects.create(
                scope_lab=lab,
                name=pspec["name"],
                goals={
                    "interests": interests,
                    "watch_topics": list(interests["areas"]),
                },
            )
            for key in pspec.get("members", []):
                ProjectMember.objects.get_or_create(project=project, user=people[key])

        attach_lab_to_department(lab, department)
        activate_department_subscription(department)
        activate_lab_subscription(lab)
        return DemoWorld.objects.create(
            key="default",
            viewer=pi,
            lab=lab,
            department=department,
            fixture_version=int(spec.get("version", 1)),
        )

    # -- ranking -----------------------------------------------------------

    def _rank(self, built: DemoWorld) -> None:
        """Rank the world now, the way a sign-up or a profile edit does, so the
        demo has feeds before the next nightly run. It calls the model for each
        target's top items, like any refit."""
        from tools._framework import services

        rec = services.get("recommendation")
        if rec is None:
            self.stdout.write(
                self.style.WARNING(
                    "  The recommendation tool is not loaded; "
                    "the nightly run will rank it."
                )
            )
            return
        people = User.objects.filter(email__iendswith="@" + demo_world.DOMAIN)
        for user in people.select_related("profile", "watch"):
            self.stdout.write(f"  ranking {user.get_full_name()} …")
            rec.refit_user(user)
        self.stdout.write(f"  ranking {built.lab.name} …")
        rec.refit_lab(built.lab)
        for project in Project.objects.filter(scope_lab=built.lab):
            self.stdout.write(f"  ranking project {project.name} …")
            rec.refit_project(project)

    def _refresh(self, built: DemoWorld) -> None:
        """The nightly run's work for the demo world alone, now: search for new
        papers on its topics and rank them, rank the open grants, conferences
        and fellowships, then write each person's and the lab's daily report.
        It calls the model as the nightly does, for nine targets."""
        from tools._framework import services

        rec = services.get("recommendation")
        if rec is None:
            raise CommandError("The recommendation tool is not loaded.")
        delivery = services.get("delivery")
        people = list(
            User.objects.filter(email__iendswith="@" + demo_world.DOMAIN)
            .select_related("profile")
            .order_by("id")
        )
        projects = list(Project.objects.filter(scope_lab=built.lab).order_by("id"))
        log = self.stdout.write

        self.stdout.write(self.style.MIGRATE_HEADING("Papers"))
        batch = rec.run_daily_batch(
            people, labs=[built.lab], projects=projects, log=log
        )
        self.stdout.write(
            f"  searched: {batch.ingest.get('new', 0)} new paper(s), "
            f"{batch.ingest.get('embedded', 0)} embedded"
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING("Grants, conferences, fellowships")
        )
        rec.run_daily_opportunities_batch(
            people, labs=[built.lab], projects=projects, prune=False, log=log
        )
        if delivery is None:
            self.stdout.write(
                self.style.WARNING("  The delivery tool is not loaded: no reports.")
            )
            return
        self.stdout.write(self.style.MIGRATE_HEADING("Daily reports"))
        for user in people:
            try:
                briefing = delivery.generate_briefing_for_user(user)
            except Exception as exc:  # noqa: BLE001 — one report must not stop the rest
                self.stderr.write(f"  {user.get_full_name()}: failed — {exc}")
                continue
            self.stdout.write(f"  {user.get_full_name()}: {briefing.origin}")
        try:
            briefing = delivery.generate_briefing_for_lab(built.lab)
            self.stdout.write(f"  {built.lab.name}: {briefing.origin}")
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"  {built.lab.name}: failed — {exc}")

    # -- status ------------------------------------------------------------

    def _status(self) -> None:
        from django.conf import settings

        built = DemoWorld.objects.select_related("viewer", "lab", "department").first()
        self.stdout.write(f"demo.enabled: {settings.DEMO_ENABLED}")
        if built is None:
            self.stdout.write("No demo world. Run `manage.py demo build`.")
            return
        people = User.objects.filter(email__iendswith="@" + demo_world.DOMAIN).count()
        self.stdout.write(
            f"World v{built.fixture_version}, built {built.built_at:%Y-%m-%d %H:%M}: "
            f"{built.lab.name} ({built.lab.slug}) in "
            f"{built.department.name if built.department else 'no department'}, "
            f"{people} people, viewing as {built.viewer.get_full_name()}."
        )
        self.stdout.write(f"Questions asked (30 days): {DemoQuestion.objects.count()}")
        self._check(built)

    def _check(self, built: DemoWorld) -> None:
        """What each target holds and how fresh it is: its matched papers and
        opportunities, when they were last ranked, and its latest daily report.
        A target ranked over a day and a half ago, or with nothing at all, is
        flagged — the nightly run has not reached it (or the demo is off)."""
        from datetime import timedelta

        from django.db.models import Count, Max
        from django.utils import timezone

        stale_before = timezone.now() - timedelta(hours=36)
        people = User.objects.filter(email__iendswith="@" + demo_world.DOMAIN).order_by(
            "id"
        )
        targets = [(u.get_full_name(), u) for u in people]
        targets.append((built.lab.name, built.lab))
        targets += [
            (f"project {p.name}", p)
            for p in Project.objects.filter(scope_lab=built.lab).order_by("id")
        ]
        flagged = 0
        self.stdout.write("Target: matches by kind · last ranked · latest report")
        for name, target in targets:
            scores = target.relevance_scores.all()
            kinds = dict(
                scores.values_list("content__type").annotate(n=Count("id")).order_by()
            )
            newest = scores.aggregate(at=Max("created_at"))["at"]
            reports = getattr(target, "daily_briefings", None)
            latest = reports.order_by("-generated_on").first() if reports else None
            stale = not kinds or newest is None or newest < stale_before
            flagged += stale
            matched = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
            line = f"  {name}: {matched or 'nothing'}"
            if newest is not None:
                line += f" · {timezone.localtime(newest):%Y-%m-%d %H:%M}"
            if reports is not None:
                line += (
                    f" · report {latest.generated_on} ({latest.origin})"
                    if latest
                    else " · no report yet"
                )
            self.stdout.write(self.style.WARNING(line) if stale else line)
        if flagged:
            self.stdout.write(
                self.style.WARNING(
                    f"{flagged} target(s) not ranked in 36 hours. "
                    "`manage.py demo refresh` runs tonight's work for them now."
                )
            )
