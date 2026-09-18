"""A synthetic research world with planted ground truth.

Everything here is fake and deterministic: the same seed and size always give
the same people, labs, projects, and papers. What makes it useful is that the
truth is known — which method each paper really uses, under which of its
names, in which field — so the knowledge graph built from it can be scored
rather than eyeballed.

Three things are planted on purpose:

* **Methods that cross fields.** A Kalman filter is used in robotics, in
  climate reanalysis, and in epidemic tracking; each field's papers call it
  something slightly different. That is what the linker must merge, what the
  field ruler must refuse to pin to one field, and what the method-bridge lane
  (CN-05) exists to find.
* **Near-miss methods.** A particle filter is not a Kalman filter; a random
  forest is not gradient boosting. Merging them is the failure the conservative
  cosine threshold exists to prevent.
* **Gaps.** Each person declares one interest they never published on and
  publishes on one method they never declared; each lab project states a need
  no member of it covers. Those are Q1's and Q2's answers, known in advance.

Institutions are real university domains from the affiliation directory,
because verified scope (CN-04) matches email domains against it. The people at
them are not real.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

#: (key, OpenAlex field id, display name). Real field ids, so the field ruler
#: can be checked against the same identifiers production uses.
FIELDS = [
    ("cs", "17", "Computer Science"),
    ("env", "23", "Environmental Science"),
    ("med", "27", "Medicine"),
    ("eng", "22", "Engineering"),
    ("earth", "19", "Earth and Planetary Sciences"),
    ("soc", "33", "Social Sciences"),
    ("econ", "20", "Economics, Econometrics and Finance"),
    ("mat", "25", "Materials Science"),
]


@dataclass(frozen=True)
class Method:
    key: str
    names: tuple[str, ...]  # canonical first; the rest are how papers vary it
    fields: tuple[str, ...]
    neutral: str
    near_miss_of: str = ""
    #: Distinctive fragments that identify this method in any wording — how the
    #: scorer recognises it in whatever terms the extractor chose.
    signature: tuple[str, ...] = ()


METHODS = [
    Method(
        "kalman",
        ("Kalman filter", "Kalman filtering", "extended Kalman filter"),
        ("eng", "earth", "med"),
        "estimating a hidden state from a sequence of noisy observations",
        signature=("kalman",),
    ),
    Method(
        "particle",
        ("particle filter", "sequential Monte Carlo"),
        ("eng", "earth"),
        "approximating a changing probability distribution with weighted samples",
        near_miss_of="kalman",
        signature=("particle filter", "monte carlo"),
    ),
    Method(
        "unet",
        ("U-Net", "U-Net segmentation network"),
        ("med", "env"),
        "labelling every pixel of an image with a class",
        signature=("u-net", "unet", "u net"),
    ),
    Method(
        "gnn",
        (
            "graph neural network",
            "graph neural networks",
            "message-passing neural network",
        ),
        ("cs", "mat", "soc"),
        "learning from the connections between entities in a network",
        signature=("graph neural", "message-passing", "message passing"),
    ),
    Method(
        "gp",
        ("Gaussian process regression", "kriging"),
        ("earth", "cs", "env"),
        "interpolating a smooth quantity between scattered measurements, "
        "with uncertainty",
        signature=("gaussian process", "kriging"),
    ),
    Method(
        "survival",
        ("survival analysis", "Cox proportional hazards model"),
        ("med", "econ", "eng"),
        "modelling how long until an event happens",
        signature=("survival", "cox ", "proportional hazards"),
    ),
    Method(
        "topic",
        ("topic modelling", "latent Dirichlet allocation"),
        ("cs", "soc"),
        "finding recurring themes across a large collection of documents",
        signature=("topic model", "latent dirichlet", "lda"),
    ),
    Method(
        "abm",
        ("agent-based model", "agent-based simulation"),
        ("med", "econ", "soc"),
        "simulating many interacting individuals to see what emerges",
        signature=("agent-based", "agent based"),
    ),
    Method(
        "did",
        ("difference-in-differences", "difference-in-differences design"),
        ("econ", "soc"),
        "comparing changes over time between a treated and an untreated group",
        signature=("difference-in-differences", "difference in differences"),
    ),
    Method(
        "fem",
        ("finite element analysis", "finite element method"),
        ("eng", "mat"),
        "splitting a physical object into small pieces to compute stress and flow",
        signature=("finite element",),
    ),
    Method(
        "transformer",
        ("transformer language model", "BERT-based language model"),
        ("cs", "med", "soc"),
        "predicting and representing text from the context around each word",
        signature=("transformer", "bert"),
    ),
    Method(
        "rf",
        ("random forest", "random forest classifier"),
        ("env", "med", "econ"),
        "combining many decision trees trained on random subsets of the data",
        signature=("random forest",),
    ),
    Method(
        "gbm",
        ("gradient boosting", "gradient-boosted trees"),
        ("cs", "econ", "mat"),
        "adding decision trees one at a time, each correcting the last",
        near_miss_of="rf",
        signature=("gradient boost", "gradient-boost"),
    ),
    Method(
        "dft",
        ("density functional theory", "DFT calculations"),
        ("mat",),
        "computing the electronic structure of a material from first principles",
        signature=("density functional", "dft"),
    ),
    Method(
        "remote",
        ("satellite remote sensing", "multispectral remote sensing"),
        ("env", "earth"),
        "measuring the ground from reflected light recorded by satellites",
        signature=("remote sensing",),
    ),
    Method(
        "bayes_hier",
        ("Bayesian hierarchical model", "hierarchical Bayesian model"),
        ("med", "soc", "earth"),
        "pooling estimates across groups while letting each group differ",
        signature=("hierarchical bayes", "bayesian hierarchical", "hierarchical model"),
    ),
]

#: Problems each field works on. Kept distinct across fields on purpose.
PROBLEMS = {
    "cs": [
        "code vulnerability detection",
        "recommender system fairness",
        "scientific text summarisation",
    ],
    "env": [
        "coral bleaching detection",
        "deforestation monitoring",
        "urban air quality mapping",
    ],
    "med": [
        "sepsis early warning",
        "hospital readmission risk",
        "tumour boundary delineation",
    ],
    "eng": [
        "robot localisation",
        "bridge fatigue monitoring",
        "battery state-of-charge estimation",
    ],
    "earth": [
        "sea surface temperature reconstruction",
        "earthquake aftershock forecasting",
        "groundwater level mapping",
    ],
    "soc": ["misinformation spread", "political polarisation", "school segregation"],
    "econ": [
        "minimum wage effects",
        "loan default prediction",
        "labour market mismatch",
    ],
    "mat": ["battery electrode degradation", "catalyst discovery", "polymer fatigue"],
}

#: Settings and data each field works in.
SETTINGS = {
    "cs": ["open-source code repositories", "arXiv abstracts", "e-commerce click logs"],
    "env": [
        "drone survey imagery",
        "Sentinel-2 satellite imagery",
        "low-cost air sensor networks",
    ],
    "med": ["intensive care unit records", "hospital discharge records", "MRI scans"],
    "eng": [
        "wheeled mobile robots",
        "strain gauge measurements",
        "lithium-ion cell cycling data",
    ],
    "earth": ["ocean buoy measurements", "seismic catalogues", "borehole records"],
    "soc": [
        "social media posts",
        "national election surveys",
        "school enrolment records",
    ],
    "econ": [
        "county employment statistics",
        "consumer loan records",
        "job vacancy postings",
    ],
    "mat": [
        "battery cycling experiments",
        "crystal structure databases",
        "tensile test specimens",
    ],
}

#: Real university domains from web/app/public/data/institutions.json.
INSTITUTIONS = [
    ("fsu.edu", "Florida State University", "US"),
    ("ufl.edu", "University of Florida", "US"),
    ("umich.edu", "University of Michigan", "US"),
    ("ox.ac.uk", "University of Oxford", "GB"),
    ("ed.ac.uk", "University of Edinburgh", "GB"),
    ("utoronto.ca", "University of Toronto", "CA"),
]

GIVEN = [
    "Ada",
    "Bo",
    "Cyrus",
    "Dana",
    "Emeka",
    "Farah",
    "Goran",
    "Hana",
    "Ines",
    "Jun",
    "Kofi",
    "Lena",
    "Mateo",
    "Nia",
    "Omar",
    "Priya",
    "Quinn",
    "Rosa",
    "Sven",
    "Tara",
    "Umar",
    "Vera",
    "Wei",
    "Xenia",
    "Yusuf",
    "Zara",
]
FAMILY = [
    "Okafor",
    "Lindqvist",
    "Tanaka",
    "Moreau",
    "Haddad",
    "Novak",
    "Reyes",
    "Kowalski",
    "Achebe",
    "Sato",
    "Brennan",
    "Duarte",
    "Ivanova",
    "Mensah",
    "Park",
    "Quispe",
    "Rahman",
    "Silva",
    "Thorne",
    "Varga",
    "Wright",
    "Yilmaz",
]


@dataclass
class Paper:
    key: str
    field: str
    problem: str
    method: str  # Method.key
    method_name: str  # the name this paper uses for it
    setting: str
    year: int


@dataclass
class Person:
    key: str
    name: str
    email: str
    institution: str
    field: str
    methods: list[str]
    declared_areas: list[str]
    declared_keywords: list[str]
    declared_skills: list[str]
    declared_only: str  # an interest they declare and never publish on
    undeclared_method: str  # a method they publish with and never declare
    papers: list[Paper] = field(default_factory=list)
    coauthors: list[str] = field(default_factory=list)


@dataclass
class ProjectSpec:
    key: str
    name: str
    lab: str
    members: list[str]
    problem: str
    methods: list[str]
    data: list[str]
    needs: list[str]
    uncovered_need: str  # stated, and no member declares it


@dataclass
class LabSpec:
    key: str
    name: str
    institution: str
    field: str
    members: list[str]
    areas: list[str]


@dataclass
class World:
    seed: int
    people: list[Person]
    labs: list[LabSpec]
    projects: list[ProjectSpec]

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def papers(self) -> list[Paper]:
        return [paper for person in self.people for paper in person.papers]


def method(key: str) -> Method:
    return next(m for m in METHODS if m.key == key)


def build(*, seed: int = 20260918, people: int = 120) -> World:
    """The world for a seed and a size. Pure: no database, no model."""
    rng = random.Random(seed)
    field_keys = [key for key, _, _ in FIELDS]
    by_field = {key: [m.key for m in METHODS if key in m.fields] for key in field_keys}

    persons: list[Person] = []
    used_names: set[str] = set()
    for index in range(people):
        home = field_keys[index % len(field_keys)]
        institution = INSTITUTIONS[(index // len(field_keys)) % len(INSTITUTIONS)][0]
        while True:
            name = f"{rng.choice(GIVEN)} {rng.choice(FAMILY)}"
            if name not in used_names:
                used_names.add(name)
                break
        own_methods = rng.sample(by_field[home], k=min(2, len(by_field[home])))
        # One method they publish with and never declare.
        extra = [m for m in by_field[home] if m not in own_methods]
        undeclared = rng.choice(extra) if extra else own_methods[-1]
        published = own_methods + (
            [undeclared] if undeclared not in own_methods else []
        )
        other_fields = [f for f in field_keys if f != home]
        declared_only = rng.choice(PROBLEMS[rng.choice(other_fields)])
        slug = name.lower().replace(" ", ".")
        person = Person(
            key=f"p{index:04d}",
            name=name,
            email=f"{slug}.{index}@{institution}",
            institution=institution,
            field=home,
            methods=published,
            declared_areas=[dict((k, n) for k, _, n in FIELDS)[home], declared_only],
            declared_keywords=[method(m).names[0] for m in own_methods],
            declared_skills=[method(own_methods[0]).names[0]],
            declared_only=declared_only,
            undeclared_method=undeclared,
        )
        count = rng.randint(3, 6)
        for n in range(count):
            method_key = published[n % len(published)]
            m = method(method_key)
            person.papers.append(
                Paper(
                    key=f"{person.key}-w{n}",
                    field=home,
                    problem=rng.choice(PROBLEMS[home]),
                    method=method_key,
                    method_name=rng.choice(m.names),
                    setting=rng.choice(SETTINGS[home]),
                    year=rng.randint(2014, 2025),
                )
            )
        persons.append(person)

    labs: list[LabSpec] = []
    projects: list[ProjectSpec] = []
    groups: dict[tuple[str, str], list[Person]] = {}
    for person in persons:
        groups.setdefault((person.institution, person.field), []).append(person)
    for (institution, home), members in sorted(groups.items()):
        for chunk_start in range(0, len(members), 6):
            chunk = members[chunk_start : chunk_start + 6]
            if len(chunk) < 2:
                continue
            key = f"lab{len(labs):03d}"
            field_name = dict((k, n) for k, _, n in FIELDS)[home]
            lab = LabSpec(
                key=key,
                name=f"{field_name} Lab {len(labs)} ({institution})",
                institution=institution,
                field=home,
                members=[p.key for p in chunk],
                areas=[field_name],
            )
            labs.append(lab)
            for person in chunk:
                person.coauthors = [p.key for p in chunk if p.key != person.key]
            covered = {m for p in chunk for m in p.methods[:2]}
            outside = [m.key for m in METHODS if m.key not in covered]
            uncovered = method(rng.choice(outside)).names[0]
            lead_methods = sorted(covered)[:2]
            projects.append(
                ProjectSpec(
                    key=f"{key}-proj",
                    name=f"{rng.choice(PROBLEMS[home]).capitalize()} project",
                    lab=key,
                    # Everyone in the lab, so Q1's answer is exactly the
                    # project's problem, its data, and the uncovered need.
                    members=[p.key for p in chunk],
                    problem=rng.choice(PROBLEMS[home]),
                    methods=[method(m).names[0] for m in lead_methods],
                    data=[rng.choice(SETTINGS[home])],
                    needs=[uncovered],
                    uncovered_need=uncovered,
                )
            )
    return World(seed=seed, people=persons, labs=labs, projects=projects)
