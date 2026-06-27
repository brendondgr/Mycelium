"""Populate the database with demo departments, labs, and people.

Generates a clean, varied organisation structure so the data model can be
explored. Every user gets an individual login — name, username,
``@demo.mycelium.test`` email, role, and a unique password — and the full
credential list is written to ``data/logins/demo_users.csv`` so you can sign in
as any of them. Every record is marked as demo data (users by email domain,
labs by a ``demo-`` slug prefix), so the command can safely clear and
regenerate, or delete, without touching real data.

    # create/refresh demo data and write the credentials file
    uv run --project web/backend python web/backend/manage.py seed_demo
    uv run --project web/backend python web/backend/manage.py seed_demo --users 600
    # add more without clearing existing demo data
    uv run --project web/backend python web/backend/manage.py seed_demo --no-clear
    # delete all demo users, labs, departments, and the credentials file
    uv run --project web/backend python web/backend/manage.py seed_demo --delete
"""

import argparse
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils.text import slugify

from apps.accounts.models import (
    AcademicTitle,
    Department,
    DeptMembership,
    Lab,
    LabMembership,
    Profile,
)

DEMO_DOMAIN = "demo.mycelium.test"
LOGINS_FILENAME = "demo_users.csv"
# Unambiguous alphabet for generated passwords (no 0/O, 1/l/I).
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

FIRST_NAMES = [
    "Ana", "Liam", "Mei", "Omar", "Sofia", "Kenji", "Priya", "Diego", "Yuki",
    "Fatima", "Noah", "Aisha", "Lucas", "Ingrid", "Mateo", "Leila", "Hiroshi",
    "Zara", "Ethan", "Nadia", "Carlos", "Hana", "Samuel", "Wei", "Elena",
    "Tariq", "Olivia", "Ravi", "Maya", "Sven", "Amara", "Daniel", "Lin",
    "Jonas", "Sara", "Kwame", "Isabel", "Arjun", "Freya", "Marco", "Camila",
    "Andre", "Nia", "Pavel", "Rosa", "Hassan", "Greta", "Theo",
]
LAST_NAMES = [
    "Garcia", "Okafor", "Nakamura", "Patel", "Johansson", "Rossi", "Chen",
    "Mwangi", "Silva", "Kim", "Muller", "Haddad", "Novak", "Andersson",
    "Reyes", "Tanaka", "Ivanova", "Oyelaran", "Costa", "Park", "Schmidt",
    "Khan", "Larsson", "Mensah", "Romano", "Wang", "Petrov", "Diallo",
    "Santos", "Lee", "Fischer", "Nasser", "Kowalski", "Lindgren", "Cruz",
    "Yamamoto", "Volkov", "Adeyemi", "Pereira", "Cho", "Weber", "Rahman",
    "Jensen", "Boateng", "Greco", "Liu", "Sokolov", "Traore", "Almeida",
    "Choi", "Hoffmann", "Karimi", "Zielinski", "Berg", "Morales", "Sato",
    "Popov", "Eze", "Ferreira", "Nguyen",
]
INSTITUTIONS = [
    "Cascadia Institute of Technology", "Northwood University",
    "Lakeshore University", "Meridian State University", "Brightwater College",
    "Granite Bay University", "Silverpine Institute", "Eastgate University",
    "Harbor City University", "Summit Research Institute",
    "Valleyfield University", "Redwood Polytechnic",
]
FIELDS = [
    "Computational Neuroscience", "Genomics", "Climate Science",
    "Machine Learning", "Synthetic Biology", "Materials Science", "Robotics",
    "Immunology", "Quantum Information", "Ecology and Evolution",
    "Bioinformatics", "Astrophysics", "Cognitive Science",
    "Chemical Engineering", "Cancer Biology", "Renewable Energy",
    "Network Science", "Microbiology", "Developmental Biology",
    "Applied Mathematics", "Human-Computer Interaction", "Structural Biology",
    "Epidemiology", "Photonics",
]
SKILLS = [
    "Python", "R", "single-cell RNA-seq", "CRISPR", "fMRI analysis",
    "deep learning", "mass spectrometry", "Bayesian modeling", "microscopy",
    "field sampling", "CFD simulation", "NLP", "electrophysiology",
    "X-ray crystallography", "graph algorithms", "statistical genetics",
    "reinforcement learning", "wet-lab automation", "time-series analysis",
    "molecular dynamics", "data visualization", "high-performance computing",
    "flow cytometry", "survey design",
]
FUNDERS = [
    "NIH", "NSF", "DOE", "DARPA", "Wellcome Trust", "HHMI",
    "Gates Foundation", "Sloan Foundation", "ERC", "Moore Foundation",
]

# Career-stage distributions for different population slices.
LAB_MEMBER_TITLES = {
    AcademicTitle.STUDENT: 0.46,
    AcademicTitle.POSTDOC: 0.24,
    AcademicTitle.RESEARCHER: 0.13,
    AcademicTitle.STAFF: 0.11,
    AcademicTitle.PI: 0.06,
}
DIRECT_DEPT_TITLES = {
    AcademicTitle.STAFF: 0.38,
    AcademicTitle.RESEARCHER: 0.30,
    AcademicTitle.PI: 0.20,
    AcademicTitle.POSTDOC: 0.12,
}
UNAFFILIATED_TITLES = {
    AcademicTitle.STUDENT: 0.42,
    AcademicTitle.RESEARCHER: 0.24,
    AcademicTitle.POSTDOC: 0.20,
    AcademicTitle.STAFF: 0.09,
    AcademicTitle.PI: 0.05,
}


class Command(BaseCommand):
    help = "Populate the database with demo departments, labs, and people."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--users",
            type=int,
            default=400,
            help="Approximate number of demo users to create (default 400).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for reproducible data (default 42).",
        )
        parser.add_argument(
            "--clear",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Clear existing demo data first (default: --clear).",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete all demo data and the credentials file, then exit.",
        )
        parser.add_argument(
            "--logins-dir",
            default=None,
            help="Directory for the credentials CSV (default: data/logins/).",
        )
        parser.add_argument(
            "--from-authors",
            default=None,
            help=(
                "Provision real profiles from a CSV of authors (columns: "
                "source,identifier) using the live importer, instead of "
                "fabricating interests. Marks them as demo data."
            ),
        )

    def handle(self, *args, **options) -> None:
        logins_path = self._logins_path(options["logins_dir"])

        if options["delete"]:
            with transaction.atomic():
                self._clear()
            removed = self._remove_logins(logins_path)
            self.stdout.write(self.style.SUCCESS("Deleted all demo data."))
            if removed:
                self.stdout.write(f"  Removed credentials file: {logins_path}")
            return

        self.passwords: dict[int, str] = {}

        if options["from_authors"]:
            self._seed_from_authors(
                options["from_authors"], clear=options["clear"]
            )
            self._export_logins(logins_path)
            self.stdout.write(
                self.style.SUCCESS(f"  Credentials written to: {logins_path}")
            )
            return

        random.seed(options["seed"])
        self.used_usernames: set[str] = set()
        self.used_slugs: set[str] = set()
        self.dept_labs: dict[str, list[Lab]] = {}

        target = options["users"]
        self.stdout.write(
            f"Creating ~{target} demo users with individual logins "
            f"(hashing passwords, this can take ~{max(2, target // 11)}s)..."
        )

        with transaction.atomic():
            if options["clear"]:
                self._clear()
            departments = self._create_departments(target)
            self._populate_labs(departments, target)
            self._create_direct_dept_members(departments)
            self._create_multi_lab_users(departments)
            self._create_pi_cross_memberships(departments)
            self._fill_unaffiliated(target)

        self._export_logins(logins_path)
        self._print_summary(logins_path)

    # -- generation helpers ------------------------------------------------

    def _clear(self) -> None:
        """Remove previously seeded demo data only.

        Departments are deleted first (their owners are PROTECT-referenced), then
        demo labs, then demo users — so no real records are touched.
        """
        domain = f"@{DEMO_DOMAIN}"
        Department.objects.filter(owner__email__endswith=domain).delete()
        Lab.objects.filter(slug__startswith="demo-").delete()
        User.objects.filter(email__endswith=domain).delete()

    def _weighted_title(self, weights: dict[str, float]) -> str:
        titles = list(weights.keys())
        return random.choices(titles, weights=list(weights.values()), k=1)[0]

    def _unique_username(self, first: str, last: str) -> str:
        base = f"{first}.{last}".lower()
        username = base
        n = 1
        while username in self.used_usernames:
            n += 1
            username = f"{base}{n}"
        self.used_usernames.add(username)
        return username

    def _unique_slug(self, base: str) -> str:
        slug = base
        n = 1
        while slug in self.used_slugs:
            n += 1
            slug = f"{base}-{n}"
        self.used_slugs.add(slug)
        return slug

    def _make_interests(self, title: str, areas: list[str]) -> dict:
        interests = {
            "version": 1,
            "areas": areas,
            "skills": random.sample(SKILLS, k=random.randint(2, 5)),
        }
        if title in (AcademicTitle.PI, AcademicTitle.POSTDOC, AcademicTitle.RESEARCHER):
            interests["funding_needs"] = random.sample(FUNDERS, k=random.randint(1, 2))
        if title == AcademicTitle.STUDENT:
            interests["seeking"] = [
                random.choice(
                    ["PhD position", "summer internship", "fellowship", "lab rotation"]
                )
            ]
        return interests

    def _make_user(
        self,
        *,
        title: str | None = None,
        title_weights: dict[str, float] | None = None,
        institution: str | None = None,
        areas: list[str] | None = None,
    ) -> User:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        username = self._unique_username(first, last)
        resolved_title = title or self._weighted_title(
            title_weights or LAB_MEMBER_TITLES
        )
        resolved_areas = areas or random.sample(FIELDS, k=random.randint(1, 3))

        password = self._password()
        user = User(
            username=username,
            email=f"{username}@{DEMO_DOMAIN}",
            first_name=first,
            last_name=last,
        )
        user.set_password(password)  # hashes with the project's real hashers
        user.save()  # post_save signal creates the Profile
        self.passwords[user.id] = password

        Profile.objects.filter(user=user).update(
            academic_title=resolved_title,
            institution=institution or "",
            interests=self._make_interests(resolved_title, resolved_areas),
        )
        return user

    def _password(self) -> str:
        return "".join(random.choice(PASSWORD_ALPHABET) for _ in range(12))

    # -- structure builders ------------------------------------------------

    def _create_departments(self, target: int) -> list[Department]:
        count = max(4, min(10, target // 50))
        fields = random.sample(FIELDS, k=count)
        departments = []
        for field in fields:
            institution = random.choice(INSTITUTIONS)
            owner = self._make_user(
                title=AcademicTitle.PI, institution=institution, areas=[field]
            )
            dept = Department.objects.create(
                owner=owner,
                name=f"Department of {field}",
                institution=institution,
            )
            DeptMembership.objects.create(
                user=owner, department=dept, role=DeptMembership.Role.OWNER
            )
            self.dept_labs[str(dept.id)] = []
            departments.append(dept)
        return departments

    def _create_lab(
        self, *, department: Department | None, institution: str, field: str
    ) -> Lab:
        lead = self._make_user(
            title=AcademicTitle.PI, institution=institution, areas=[field]
        )
        lab = Lab.objects.create(
            name=f"{lead.last_name} Lab",
            slug=self._unique_slug(f"demo-{slugify(lead.last_name)}-lab"),
            department=department,
        )
        LabMembership.objects.create(
            user=lead, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
        )

        # A senior lab manager (admin) for roughly half of the labs.
        if random.random() < 0.5:
            manager = self._make_user(
                title=random.choice([AcademicTitle.STAFF, AcademicTitle.POSTDOC]),
                institution=institution,
                areas=[field],
            )
            LabMembership.objects.create(
                user=manager, lab=lab, role=LabMembership.Role.ADMIN
            )

        for _ in range(random.randint(5, 11)):
            title = self._weighted_title(LAB_MEMBER_TITLES)
            member = self._make_user(
                title=title,
                institution=institution,
                areas=random.sample([field, *random.sample(FIELDS, k=2)], k=2),
            )
            # An occasional second PI (co-lead) or a viewer (external collaborator).
            if title == AcademicTitle.PI and random.random() < 0.5:
                role, is_lead = LabMembership.Role.MEMBER, True
            elif random.random() < 0.08:
                role, is_lead = LabMembership.Role.VIEWER, False
            else:
                role, is_lead = LabMembership.Role.MEMBER, False
            LabMembership.objects.create(
                user=member, lab=lab, role=role, is_lead=is_lead
            )

        if department is not None:
            self.dept_labs[str(department.id)].append(lab)
        return lab

    def _populate_labs(self, departments: list[Department], target: int) -> None:
        for dept in departments:
            field = dept.name.removeprefix("Department of ")
            for _ in range(random.randint(2, 4)):
                self._create_lab(
                    department=dept,
                    institution=dept.institution,
                    field=random.choice([field, random.choice(FIELDS)]),
                )
        for _ in range(max(3, target // 70)):
            self._create_lab(
                department=None,
                institution=random.choice(INSTITUTIONS),
                field=random.choice(FIELDS),
            )

    def _create_direct_dept_members(self, departments: list[Department]) -> None:
        """Single users attached straight to a department, not via any lab."""
        for dept in departments:
            for _ in range(random.randint(3, 7)):
                member = self._make_user(
                    title_weights=DIRECT_DEPT_TITLES,
                    institution=dept.institution,
                )
                role = random.choices(
                    [
                        DeptMembership.Role.ADMIN,
                        DeptMembership.Role.MEMBER,
                        DeptMembership.Role.VIEWER,
                    ],
                    weights=[0.25, 0.6, 0.15],
                    k=1,
                )[0]
                DeptMembership.objects.create(
                    user=member, department=dept, role=role
                )

    def _create_multi_lab_users(self, departments: list[Department]) -> None:
        """Users who belong to two labs of the same department (counted once in
        the derived department membership)."""
        for dept in departments:
            labs = self.dept_labs[str(dept.id)]
            if len(labs) < 2:
                continue
            for _ in range(random.randint(1, 2)):
                member = self._make_user(
                    title=random.choice(
                        [AcademicTitle.POSTDOC, AcademicTitle.RESEARCHER]
                    ),
                    institution=dept.institution,
                )
                for lab in random.sample(labs, k=2):
                    LabMembership.objects.create(
                        user=member, lab=lab, role=LabMembership.Role.MEMBER
                    )

    def _create_pi_cross_memberships(self, departments: list[Department]) -> None:
        """A PI who leads one lab and is a plain member of another (briefing §5)."""
        leads = list(
            LabMembership.objects.filter(
                is_lead=True, user__email__endswith=f"@{DEMO_DOMAIN}"
            ).select_related("lab", "user")[:20]
        )
        random.shuffle(leads)
        for lead_membership in leads[:6]:
            other_labs = Lab.objects.filter(slug__startswith="demo-").exclude(
                memberships__user=lead_membership.user
            )
            other = other_labs.order_by("?").first()
            if other is None:
                continue
            LabMembership.objects.create(
                user=lead_membership.user,
                lab=other,
                role=LabMembership.Role.MEMBER,
                is_lead=False,
            )

    def _fill_unaffiliated(self, target: int) -> None:
        """Solo users with no lab or department membership."""
        while self._demo_user_count() < target:
            self._make_user(
                title_weights=UNAFFILIATED_TITLES,
                institution=random.choice([*INSTITUTIONS, "", ""]),
            )

    def _seed_from_authors(self, csv_path: str, *, clear: bool) -> None:
        """Provision real profiles from a CSV using the live author importer.

        The CSV needs ``source`` and ``identifier`` columns. Each row hits the
        network through ``provision_from_author`` (so this is a manual, on-demand
        mode, never part of the test suite). Failures are reported and skipped.
        """
        from apps.accounts.provisioning import provision_from_author

        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"authors file not found: {path}")

        with path.open(newline="", encoding="utf-8") as fh:
            authors = [row for row in csv.DictReader(fh)]

        with transaction.atomic():
            if clear:
                self._clear()

        created = 0
        for row in authors:
            source = (row.get("source") or "").strip()
            identifier = (row.get("identifier") or row.get("id") or "").strip()
            if not source or not identifier:
                self.stderr.write(f"  skip (missing source/identifier): {row}")
                continue
            try:
                result = provision_from_author(
                    identifier, source, email_domain=DEMO_DOMAIN
                )
            except Exception as exc:  # noqa: BLE001 - report and continue
                self.stderr.write(f"  skip {source}:{identifier}: {exc}")
                continue
            self.passwords[result.user.id] = result.credentials["password"]
            created += 1
            self.stdout.write(
                f"  provisioned {result.credentials['username']} "
                f"from {source}:{identifier}"
            )

        self.stdout.write(
            self.style.SUCCESS(f"Provisioned {created} author profile(s).")
        )

    # -- credentials export ------------------------------------------------

    def _logins_path(self, logins_dir: str | None) -> Path:
        if logins_dir:
            return Path(logins_dir) / LOGINS_FILENAME
        # settings.BASE_DIR is web/backend; the repo root is two levels up.
        repo_root = Path(settings.BASE_DIR).parent.parent
        return repo_root / "data" / "logins" / LOGINS_FILENAME

    def _remove_logins(self, logins_path: Path) -> bool:
        if logins_path.exists():
            logins_path.unlink()
            return True
        return False

    def _export_logins(self, logins_path: Path) -> int:
        """Write every demo user's credentials to a CSV, role first.

        The ``role`` column is the headline: ``department`` (department head),
        ``lab`` (lab leader / PI), or ``user`` (everyone else).
        """
        domain = f"@{DEMO_DOMAIN}"
        dept_heads = dict(
            Department.objects.filter(owner__email__endswith=domain).values_list(
                "owner_id", "name"
            )
        )
        lab_leads: dict[int, tuple[str, str]] = {}
        for uid, lab_name, dept_name in LabMembership.objects.filter(
            is_lead=True, user__email__endswith=domain
        ).values_list("user_id", "lab__name", "lab__department__name"):
            lab_leads.setdefault(uid, (lab_name, dept_name or ""))

        labs_by_user: dict[int, list[str]] = defaultdict(list)
        for uid, lab_name in LabMembership.objects.filter(
            user__email__endswith=domain
        ).values_list("user_id", "lab__name"):
            labs_by_user[uid].append(lab_name)
        depts_by_user: dict[int, list[str]] = defaultdict(list)
        for uid, dept_name in DeptMembership.objects.filter(
            user__email__endswith=domain
        ).values_list("user_id", "department__name"):
            depts_by_user[uid].append(dept_name)
        profiles = {
            row[0]: row[1:]
            for row in Profile.objects.filter(
                user__email__endswith=domain
            ).values_list(
                "user_id",
                "academic_title",
                "institution",
                "orcid",
                "openalex_id",
                "scholar_id",
            )
        }

        rows = []
        for uid, username, email, first, last in User.objects.filter(
            email__endswith=domain
        ).values_list("id", "username", "email", "first_name", "last_name"):
            if uid in dept_heads:
                role, affiliation = "department", f"heads {dept_heads[uid]}"
            elif uid in lab_leads:
                lab_name, dept_name = lab_leads[uid]
                where = f" ({dept_name})" if dept_name else " (standalone)"
                role, affiliation = "lab", f"leads {lab_name}{where}"
            elif labs_by_user.get(uid):
                role, affiliation = "user", "member of " + ", ".join(labs_by_user[uid])
            elif depts_by_user.get(uid):
                role = "user"
                affiliation = "dept member of " + ", ".join(depts_by_user[uid])
            else:
                role, affiliation = "user", "unaffiliated"
            title, institution, orcid, openalex_id, scholar_id = profiles.get(
                uid, ("", "", "", "", "")
            )
            rows.append(
                {
                    "role": role,
                    "name": f"{first} {last}".strip(),
                    "username": username,
                    "email": email,
                    "password": self.passwords.get(uid, ""),
                    "academic_title": title,
                    "institution": institution,
                    "affiliation": affiliation,
                    "orcid": orcid,
                    "openalex_id": openalex_id,
                    "scholar_id": scholar_id,
                }
            )

        role_rank = {"department": 0, "lab": 1, "user": 2}
        rows.sort(key=lambda r: (role_rank[r["role"]], r["name"]))

        logins_path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "role", "name", "username", "email", "password",
            "academic_title", "institution", "affiliation",
            "orcid", "openalex_id", "scholar_id",
        ]
        with logins_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    # -- reporting ---------------------------------------------------------

    def _demo_user_count(self) -> int:
        return User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}").count()

    def _print_summary(self, logins_path: Path) -> None:
        domain = f"@{DEMO_DOMAIN}"
        users = User.objects.filter(email__endswith=domain)
        labs = Lab.objects.filter(slug__startswith="demo-")
        depts = Department.objects.filter(owner__email__endswith=domain)

        in_dept_lab = (
            users.filter(lab_memberships__lab__department__isnull=False)
            .distinct()
            .count()
        )
        standalone_lab = (
            users.filter(
                lab_memberships__lab__department__isnull=True,
                lab_memberships__isnull=False,
            )
            .distinct()
            .count()
        )
        direct_dept = (
            users.filter(dept_memberships__isnull=False, lab_memberships__isnull=True)
            .distinct()
            .count()
        )
        multi_lab = (
            users.annotate(n=Count("lab_memberships", distinct=True))
            .filter(n__gte=2)
            .count()
        )
        unaffiliated = users.filter(
            lab_memberships__isnull=True, dept_memberships__isnull=True
        ).count()
        leads = LabMembership.objects.filter(
            is_lead=True, user__email__endswith=domain
        ).count()
        titles = Counter(
            Profile.objects.filter(user__email__endswith=domain).values_list(
                "academic_title", flat=True
            )
        )

        write = self.stdout.write
        write(self.style.SUCCESS("Seeded demo data:"))
        write(f"  Departments:            {depts.count()}")
        write(
            f"  Labs:                   {labs.count()} "
            f"({labs.filter(department__isnull=False).count()} in departments, "
            f"{labs.filter(department__isnull=True).count()} standalone)"
        )
        write(f"  Users:                  {users.count()}")
        write(f"    Lab leads (PIs):              {leads}")
        write(f"    In a lab within a department: {in_dept_lab}")
        write(f"    In a standalone lab:          {standalone_lab}")
        write(f"    Direct department members:    {direct_dept}")
        write(f"    In multiple labs:             {multi_lab}")
        write(f"    Unaffiliated individuals:     {unaffiliated}")
        lab_ms = LabMembership.objects.filter(user__email__endswith=domain).count()
        dept_ms = DeptMembership.objects.filter(user__email__endswith=domain).count()
        write(f"  Memberships:            {lab_ms} lab, {dept_ms} dept")
        write("  Academic titles:        " + ", ".join(
            f"{title}={count}" for title, count in sorted(titles.items())
        ))
        write(self.style.SUCCESS(f"  Credentials written to: {logins_path}"))
        write(
            "  Role column: department (head) / lab (leader) / user. "
            "Sign in with the username + password from the file."
        )
