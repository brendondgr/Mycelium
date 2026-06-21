"""Populate the database with demo departments, labs, and people.

Generates a clean, varied organisation structure so the data model can be
explored. Every record it creates is marked as demo data — users get a
``@demo.mycelium.test`` email and labs get a ``demo-`` slug prefix — so the
command can safely clear and regenerate without touching real data.

    uv run --project web/backend python web/backend/manage.py seed_demo
    uv run --project web/backend python web/backend/manage.py seed_demo --users 600
    uv run --project web/backend python web/backend/manage.py seed_demo --no-clear
"""

import argparse
import random
from collections import Counter

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
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
DEMO_PASSWORD = "demo-pass-123"

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

    def handle(self, *args, **options) -> None:
        random.seed(options["seed"])
        self.password_hash = make_password(DEMO_PASSWORD)
        self.used_usernames: set[str] = set()
        self.used_slugs: set[str] = set()
        self.dept_labs: dict[str, list[Lab]] = {}

        target = options["users"]

        with transaction.atomic():
            if options["clear"]:
                self._clear()
            departments = self._create_departments(target)
            self._populate_labs(departments, target)
            self._create_direct_dept_members(departments)
            self._create_multi_lab_users(departments)
            self._create_pi_cross_memberships(departments)
            self._fill_unaffiliated(target)

        self._print_summary()

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
            "areas": areas,
            "skills": random.sample(SKILLS, k=random.randint(2, 5)),
        }
        if title in (AcademicTitle.PI, AcademicTitle.POSTDOC, AcademicTitle.RESEARCHER):
            interests["funding_needs"] = random.sample(FUNDERS, k=random.randint(1, 2))
        if title == AcademicTitle.STUDENT:
            interests["seeking"] = random.choice(
                ["PhD position", "summer internship", "fellowship", "lab rotation"]
            )
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

        user = User(
            username=username,
            email=f"{username}@{DEMO_DOMAIN}",
            first_name=first,
            last_name=last,
        )
        user.password = self.password_hash
        user.save()  # post_save signal creates the Profile

        Profile.objects.filter(user=user).update(
            academic_title=resolved_title,
            institution=institution or "",
            interests=self._make_interests(resolved_title, resolved_areas),
        )
        return user

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

    # -- reporting ---------------------------------------------------------

    def _demo_user_count(self) -> int:
        return User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}").count()

    def _print_summary(self) -> None:
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
        write(self.style.SUCCESS(
            f"  Sign in as any user with password: {DEMO_PASSWORD}"
        ))
