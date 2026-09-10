"""Seed a simulated FSU Department of Scientific Computing plus its PULSE Lab.

A named-people counterpart to ``seed_demo``: instead of fabricating an org chart,
this builds one department whose roster mirrors a real, public one (FSU's
Department of Scientific Computing core faculty and graduate students, plus the
PULSE Lab team) so the department and lab surfaces can be reviewed with a roster
that looks and reads like a real one.

**No real contact details are used.** Names are public roster names; every email
is synthesized under ``SIM_DOMAIN``, whose ``.invalid`` top-level domain is
reserved by RFC 2606 and can never resolve or deliver. That is deliberate — a
simulated roster must not be reachable by any mail the product sends. The domain
also differs from ``seed_demo``'s, so ``seed_demo --delete`` never touches these
rows and vice versa.

Research areas are **inferred** from each person's public field, not scraped: the
department's own pages gate interests behind a login. They exist to give the
scan → rank → suggest pipeline something plausible to work with, not to describe
anyone's actual research.

Structure it builds (see ``docs/repo-map.md``, "Backend — identity & organization"):

* Department of Scientific Computing, owned by its chair, on an **active** Canopy
  plan that seats the whole roster.
* An ``--admin`` user placed on the department as ADMIN.
* The PULSE Lab attached to the department but **excluded from its plan**
  (``department_plan_included=False``), holding its **own** active Lab plan. That
  is what makes the lab function separately: it sits under the department for
  visibility while paying for and entitling its own members.

    uv run --project web/backend python web/backend/manage.py seed_fsu_sc
    uv run --project web/backend python web/backend/manage.py seed_fsu_sc --delete
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import (
    AcademicTitle,
    Department,
    DeptMembership,
    Lab,
    LabMembership,
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

#: RFC 2606 reserves ``.invalid``; nothing addressed here can ever be delivered.
SIM_DOMAIN = "fsu-sc.mycelium.invalid"
LOGINS_FILENAME = "fsu_sc_users.csv"
INSTITUTION = "Florida State University"
DEPARTMENT_NAME = "Department of Scientific Computing"
LAB_NAME = "PULSE Lab"
LAB_SLUG = "pulse-lab"
LAB_STATEMENT = (
    "Scientific machine learning for oceanography and health: deep learning "
    "surrogates for ocean forecasting and data assimilation, and medical image "
    "analysis for clinical decision support."
)
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# -- Core faculty (public roster). Areas are inferred from each person's field. --
FACULTY: list[tuple[str, str, list[str]]] = [
    ("Peter", "Beerli",
     ["population genetics", "coalescent theory", "Bayesian inference"]),
    ("Hristo", "Chipilski",
     ["data assimilation", "numerical weather prediction",
      "machine learning for atmospheric science"]),
    ("Nicholas", "Dexter",
     ["uncertainty quantification", "approximation theory",
      "deep learning for PDEs"]),
    ("Gordon", "Erlebacher",
     ["data science", "scientific visualization", "GPU computing"]),
    ("Milinda", "Fernando",
     ["adaptive mesh refinement", "numerical relativity",
      "high-performance computing"]),
    ("Chen", "Huang",
     ["density functional theory", "quantum chemistry", "materials modeling"]),
    ("Tommie", "Juzek",
     ["computational linguistics", "natural language processing",
      "corpus linguistics"]),
    ("Alan", "Lemmon",
     ["phylogenetics", "evolutionary genomics", "sequence capture"]),
    ("Anke", "Meyer-Baese",
     ["medical imaging", "computational neuroscience",
      "machine learning in biomedicine"]),
    ("Tomasz", "Plewa",
     ["computational astrophysics", "hydrodynamics", "supernova simulation"]),
    ("Bryan", "Quaife",
     ["computational fluid dynamics", "boundary integral methods",
      "wildfire modeling"]),
    ("Sachin", "Shanbhag",
     ["polymer rheology", "soft matter", "molecular simulation"]),
    ("Xiaoqiang", "Wang",
     ["numerical PDEs", "phase field models", "image processing"]),
    ("Olmo", "Zavala Romero",
     ["scientific machine learning", "ocean forecasting",
      "medical image analysis"]),
]

#: The chair, who owns the department.
DEPARTMENT_HEAD = ("Peter", "Beerli")
#: The PULSE PI, who owns the lab.
LAB_LEAD = ("Olmo", "Zavala Romero")

# -- Graduate students (public roster). Interests are login-gated upstream, so
# each is given areas drawn deterministically from the department's own fields. --
GRAD_STUDENTS: list[tuple[str, str]] = [
    ("Emmanuella", "Ababio"),
    ("Syed Arsal", "Ahmed"),
    ("Stephen", "Asare"),
    ("Jianing", "Chen"),
    ("Jonathan", "Gardner"),
    ("Temesghen", "Ghirmai"),
    ("Utshab Kumar", "Ghosh"),
    ("Jhamieka", "Greenwood"),
    ("Lasitha", "Gunasekara"),
    ("Brendon", "Gutierrez"),
    ("Nyeng", "Gyang"),
    ("Iffat", "Jahan"),
    ("Robert", "Joseph"),
    ("Kunal", "Kanawade"),
    ("Young Hwan", "Kim"),
    ("Colby", "Leavitt"),
    ("Jose", "Miranda"),
    ("Jabarrie", "Monsano"),
    ("Ari", "Moscatel"),
    ("Eesha", "Mukherjee"),
    ("Zachary", "Mullaghy"),
    ("Tara", "Niakan"),
    ("Abhina", "Premachandran Bindu"),
    ("Kazi Md", "Sadat"),
    ("Samuel", "Samlut"),
    ("Shifur Rahman", "Shakil"),
    ("MJ", "Shooshtari"),
    ("Rithika", "Shyam Kumar"),
    ("Farhana", "Taiyebah"),
    ("Mani", "Tyagi"),
    ("Jorge Eduardo", "Velasco Zavala"),
    ("Yifan", "Wang"),
    ("Liam", "White"),
    ("Charithma", "Wickramasinghe Thanthirige"),
]

#: PULSE areas, given to every lab member so the lab's derived profile is coherent.
PULSE_AREAS = [
    "scientific machine learning",
    "ocean forecasting",
    "deep learning surrogates",
    "medical image analysis",
]

# PULSE roster beyond the PI. ``(first, last, title, lab_role, is_dept_grad)``.
# ``is_dept_grad`` marks the people who also appear on the department's graduate
# roster, so they are one user holding both memberships rather than two people.
LAB_TEAM: list[tuple[str, str, str, str, bool]] = [
    ("Pedro", "Segura",
     AcademicTitle.POSTDOC, LabMembership.Role.MEMBER, False),
    ("Jose", "Miranda",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, True),
    ("Eesha", "Mukherjee",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, True),
    ("Iffat", "Jahan",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, True),
    ("Jorge Eduardo", "Velasco Zavala",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, True),
    ("Yifan", "Wang",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, True),
    ("Alexis", "Staveski",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, False),
    ("Cole", "Pridgen",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, False),
    ("Sofia", "Rojas",
     AcademicTitle.STUDENT, LabMembership.Role.MEMBER, False),
    ("Nishad", "Nakhwa",
     AcademicTitle.RESEARCHER, LabMembership.Role.VIEWER, False),
]

#: The grad-roster entry that is the ``--admin`` account rather than a new person.
ADMIN_ROSTER_NAME = ("Brendon", "Gutierrez")


class Command(BaseCommand):
    help = (
        "Seed a simulated FSU Department of Scientific Computing plus the PULSE "
        "Lab, using public roster names and non-deliverable synthetic emails."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--admin",
            default="brendondgr",
            help="Existing username to place on the department as ADMIN.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=7,
            help="Random seed for the generated areas and passwords (default 7).",
        )
        parser.add_argument(
            "--logins-dir",
            default=None,
            help="Directory for the credentials CSV (default: data/logins/).",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete the simulated department, lab, people, and CSV, then exit.",
        )

    # -- entrypoint --------------------------------------------------------

    def handle(self, *args, **options) -> None:
        logins_path = self._logins_path(options["logins_dir"])

        if options["delete"]:
            with transaction.atomic():
                self._clear()
            if logins_path.exists():
                logins_path.unlink()
                self.stdout.write(f"  Removed credentials file: {logins_path}")
            self.stdout.write(self.style.SUCCESS("Deleted the simulated FSU data."))
            return

        try:
            admin = User.objects.get(username=options["admin"])
        except User.DoesNotExist:
            raise CommandError(
                f"No user named {options['admin']!r}. Pass --admin <username> "
                "with an account that already exists."
            ) from None

        random.seed(options["seed"])
        self.passwords: dict[int, str] = {}
        self.people: dict[tuple[str, str], User] = {}

        with transaction.atomic():
            self._clear()
            self._verify(admin)
            self._create_faculty()
            self._create_grad_students(admin)
            department = self._build_department(admin)
            lab = self._build_lab(department, admin)

        self._export_logins(logins_path)
        self._summarize(department, lab, admin, logins_path)

    # -- teardown ----------------------------------------------------------

    def _clear(self) -> None:
        """Remove only this command's rows.

        The department goes first (its owner is PROTECT-referenced), then the lab
        by its known slug, then the simulated people by email domain. The
        ``--admin`` account is never a simulated person, so it survives; only its
        memberships go, with the orgs they belonged to.
        """
        domain = f"@{SIM_DOMAIN}"
        Department.objects.filter(name=DEPARTMENT_NAME).delete()
        Lab.objects.filter(slug=LAB_SLUG).delete()
        User.objects.filter(email__endswith=domain).delete()

    # -- people ------------------------------------------------------------

    def _verify(self, user: User) -> None:
        """Mark one account active and email-verified.

        Verification is a real gate: an unverified profile is refused by the org
        endpoints, so a simulated roster that is not verified cannot be clicked
        through on the site.
        """
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        Profile.objects.filter(user=user).update(is_verified=True)

    def _password(self) -> str:
        return "".join(random.choice(PASSWORD_ALPHABET) for _ in range(12))

    def _username(self, first: str, last: str) -> str:
        """``first.last`` lowercased, spaces and hyphens folded to dots."""
        raw = f"{first}.{last}".lower()
        cleaned = "".join(c if c.isalnum() else "." for c in raw)
        while ".." in cleaned:
            cleaned = cleaned.replace("..", ".")
        return cleaned.strip(".")

    def _make_person(
        self,
        first: str,
        last: str,
        *,
        title: str,
        areas: list[str],
        seeking: str | None = None,
    ) -> User:
        username = self._username(first, last)
        password = self._password()
        user = User(
            username=username,
            email=f"{username}@{SIM_DOMAIN}",
            first_name=first,
            last_name=last,
            is_active=True,
        )
        user.set_password(password)
        user.save()  # post_save signal creates the Profile
        self.passwords[user.id] = password

        interests: dict = {
            "version": 1,
            "statement": (
                f"{first} {last} works on {', '.join(areas)} in the "
                f"{DEPARTMENT_NAME} at {INSTITUTION}."
            ),
            "areas": areas,
            "keywords": list(areas),
        }
        if title == AcademicTitle.PI:
            interests["funding_needs"] = ["NSF", "NIH", "DOE"]
        if seeking:
            interests["seeking"] = [seeking]

        Profile.objects.filter(user=user).update(
            academic_title=title,
            institution=INSTITUTION,
            interests=interests,
            is_verified=True,
        )
        # Watch topics are the sole source of literature-scan queries, so a
        # person with none is invisible to the nightly run.
        WatchPreference.objects.update_or_create(
            user=user, defaults={"topics": list(areas)}
        )
        self.people[(first, last)] = user
        return user

    def _create_faculty(self) -> None:
        for first, last, areas in FACULTY:
            self._make_person(first, last, title=AcademicTitle.PI, areas=areas)

    def _create_grad_students(self, admin: User) -> None:
        """Create every graduate student except the one that is the admin account.

        The admin already exists as a real account and appears on the public
        graduate roster, so reusing it keeps one person as one user instead of
        seeding a duplicate alongside them.
        """
        pulse_grads = {
            (first, last) for first, last, _, _, is_grad in LAB_TEAM if is_grad
        }
        faculty_areas = [area for _, _, areas in FACULTY for area in areas]
        for first, last in GRAD_STUDENTS:
            if (first, last) == ADMIN_ROSTER_NAME:
                self.people[(first, last)] = admin
                continue
            if (first, last) in pulse_grads:
                areas = random.sample(PULSE_AREAS, k=3)
            else:
                areas = random.sample(faculty_areas, k=3)
            self._make_person(
                first,
                last,
                title=AcademicTitle.STUDENT,
                areas=areas,
                seeking=random.choice(
                    ["PhD funding", "summer internship", "fellowship",
                     "conference travel"]
                ),
            )

    # -- structure ---------------------------------------------------------

    def _build_department(self, admin: User) -> Department:
        """Stand the department up on an active Canopy plan seating everyone."""
        head = self.people[DEPARTMENT_HEAD]
        result = create_department_workspace(
            head, DEPARTMENT_NAME, institution=INSTITUTION
        )
        department = result.department
        department.profile.statement = (
            "Interdisciplinary computational science at Florida State University: "
            "numerical methods, high-performance computing, and machine learning "
            "applied across the physical and life sciences."
        )
        department.profile.areas = [
            area for _, _, areas in FACULTY for area in areas[:1]
        ]
        department.profile.save(update_fields=["statement", "areas", "updated_at"])

        DeptMembership.objects.update_or_create(
            user=admin,
            department=department,
            defaults={"role": DeptMembership.Role.ADMIN},
        )
        for first, last, _ in FACULTY:
            if (first, last) == DEPARTMENT_HEAD:
                continue  # already OWNER
            DeptMembership.objects.update_or_create(
                user=self.people[(first, last)],
                department=department,
                defaults={"role": DeptMembership.Role.MEMBER},
            )
        for first, last in GRAD_STUDENTS:
            user = self.people[(first, last)]
            if user == admin:
                continue  # already ADMIN
            DeptMembership.objects.update_or_create(
                user=user,
                department=department,
                defaults={"role": DeptMembership.Role.MEMBER},
            )

        # Activation is what turns the free structure into a working plan: it
        # opens the period and seats every plan member ACTIVE.
        activate_department_subscription(department)
        return department

    def _build_lab(self, department: Department, admin: User) -> Lab:
        """Stand the lab up on its **own** active plan, under the department.

        Attached for visibility, excluded from the department's plan. That
        combination is the point: the lab's members are seated and entitled by
        the lab's own subscription, so the lab keeps working whatever the
        department does with its plan.
        """
        lead = self.people[LAB_LEAD]
        result = create_lab_workspace(lead, LAB_NAME)
        lab = result.lab
        if lab.slug != LAB_SLUG:
            lab.slug = LAB_SLUG
            lab.save(update_fields=["slug", "updated_at"])
        lab.profile.statement = LAB_STATEMENT
        lab.profile.areas = list(PULSE_AREAS)
        lab.profile.save(update_fields=["statement", "areas", "updated_at"])

        LabMembership.objects.update_or_create(
            user=admin,
            lab=lab,
            defaults={"role": LabMembership.Role.ADMIN, "is_lead": False},
        )
        for first, last, title, role, _is_grad in LAB_TEAM:
            user = self.people.get((first, last))
            if user is None:
                user = self._make_person(
                    first,
                    last,
                    title=title,
                    areas=random.sample(PULSE_AREAS, k=3),
                    seeking="research assistantship"
                    if title == AcademicTitle.STUDENT
                    else None,
                )
            LabMembership.objects.update_or_create(
                user=user, lab=lab, defaults={"role": role, "is_lead": False}
            )

        attach_lab_to_department(lab, department)
        # Left excluded (the default): inclusion would re-seat these members on
        # the department's plan, which is exactly the coupling we do not want.
        activate_lab_subscription(lab)
        return lab

    # -- output ------------------------------------------------------------

    def _logins_path(self, logins_dir: str | None) -> Path:
        if logins_dir:
            return Path(logins_dir) / LOGINS_FILENAME
        # settings.BASE_DIR is web/backend; the repo root is two levels up.
        repo_root = Path(settings.BASE_DIR).parent.parent
        return repo_root / "data" / "logins" / LOGINS_FILENAME

    def _export_logins(self, logins_path: Path) -> int:
        """Write each simulated person's credentials, with where they sit."""
        domain = f"@{SIM_DOMAIN}"
        dept_roles = dict(
            DeptMembership.objects.filter(department__name=DEPARTMENT_NAME).values_list(
                "user_id", "role"
            )
        )
        lab_roles = dict(
            LabMembership.objects.filter(lab__slug=LAB_SLUG).values_list(
                "user_id", "role"
            )
        )
        titles = dict(
            Profile.objects.filter(user__email__endswith=domain).values_list(
                "user_id", "academic_title"
            )
        )

        rows = []
        for uid, username, email, first, last in (
            User.objects.filter(email__endswith=domain)
            .order_by("last_name", "first_name")
            .values_list("id", "username", "email", "first_name", "last_name")
        ):
            rows.append(
                {
                    "name": f"{first} {last}".strip(),
                    "username": username,
                    "email": email,
                    "password": self.passwords.get(uid, ""),
                    "academic_title": titles.get(uid, ""),
                    "department_role": dept_roles.get(uid, ""),
                    "lab_role": lab_roles.get(uid, ""),
                    "institution": INSTITUTION,
                }
            )

        logins_path.parent.mkdir(parents=True, exist_ok=True)
        with logins_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def _summarize(
        self, department: Department, lab: Lab, admin: User, logins_path: Path
    ) -> None:
        from apps.accounts.services import effective_member_count

        self.stdout.write(self.style.SUCCESS(f"Created {department.name}"))
        self.stdout.write(f"  Institution:  {department.institution}")
        self.stdout.write(f"  Head (owner): {department.owner.get_full_name()}")
        self.stdout.write(f"  Admin:        {admin.username}")
        self.stdout.write(
            f"  Direct members: {department.memberships.count()} "
            f"(effective: {effective_member_count(department)})"
        )
        self.stdout.write(self.style.SUCCESS(f"Created {lab.name} ({lab.slug})"))
        self.stdout.write(f"  In department:  {lab.department.name}")
        self.stdout.write(
            f"  On dept plan:   {lab.department_plan_included} "
            "(runs on its own Lab plan)"
        )
        self.stdout.write(f"  Members:        {lab.memberships.count()}")
        self.stdout.write(f"  Credentials:    {logins_path}")
        self.stdout.write(
            f"  Emails use the non-deliverable domain @{SIM_DOMAIN}."
        )
