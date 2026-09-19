"""The synthetic ambient world: labs, people, and what each of them will say.

Everything here is deterministic from the seed and touches no database. A
**plant** is one thing a person will say in a known conversation on a known
day — a preference, a capability, a colleague's idea, a told project fact —
with the outcome deliberation should reach for its topic. The conversations
around the plants are written later by the model (:mod:`.converse`); the truth
is fixed here first.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

#: Distinct research topics. Drawn without replacement, so no two plants of
#: one person share a topic and the linker has no near-duplicates to merge.
TOPICS = """
conformal prediction; gaussian processes; kriging; causal inference;
variational autoencoders; graph neural networks; contrastive learning;
bayesian optimisation; survival analysis; topic modelling; diffusion models;
reinforcement learning from human feedback; federated learning;
differential privacy; mixed effects models; structural equation modelling;
agent based modelling; finite element analysis; spectral clustering;
hidden markov models; transformer interpretability; active learning;
knowledge distillation; symbolic regression; optimal transport;
normalising flows; sparse autoencoders; neural radiance fields;
time series forecasting; anomaly detection; object detection;
semantic segmentation; speech recognition; machine translation;
protein structure prediction; single cell sequencing; metagenomics;
phylogenetic inference; species distribution models; remote sensing;
lidar point clouds; climate downscaling; hydrological modelling;
epidemic modelling; propensity score matching; instrumental variables;
difference in differences; regression discontinuity; qualitative coding;
grounded theory; discourse analysis; ethnographic fieldwork;
eye tracking; electroencephalography; functional mri analysis;
spiking neural networks; neuromorphic hardware; quantum error correction;
tensor networks; molecular dynamics; density functional theory;
crystal structure prediction; battery degradation modelling;
power grid optimisation; traffic flow simulation; robot grasping;
motion planning; simultaneous localisation and mapping; soft robotics;
human robot interaction; wearable sensing; gait analysis;
medical image registration; histopathology slides; radiology report generation;
clinical trial emulation; electronic health records; drug repurposing;
antimicrobial resistance; vaccine hesitancy surveys; wastewater surveillance;
social network analysis; misinformation detection; stance detection;
argument mining; legal text classification; code generation;
program synthesis; static analysis; fuzz testing; formal verification;
smart contract auditing; recommender systems; learning to rank;
query expansion; retrieval augmented generation; entity linking;
knowledge graph embeddings; ontology alignment; data provenance;
record linkage; synthetic data generation; data augmentation;
curriculum learning; meta learning; continual learning; model compression;
quantisation aware training; mixture of experts; speculative decoding;
prompt injection defences; red teaming; fairness auditing;
explainable credit scoring; algorithmic pricing; auction design;
mechanism design; game theoretic security; supply chain optimisation;
inventory forecasting; queueing models; stochastic scheduling;
coral reef monitoring; bird song classification; camera trap images;
soil carbon mapping; crop yield prediction; precision irrigation;
glacier melt modelling; ocean acidification; urban heat islands;
air quality sensing; noise pollution mapping; building energy modelling;
earthquake early warning; landslide susceptibility; wildfire spread;
flood inundation mapping; archaeological lidar; digital humanities;
historical handwriting recognition; music information retrieval;
choreography analysis; game level generation; procedural animation;
virtual reality locomotion; haptic feedback; accessibility auditing;
sign language recognition; child language acquisition; second language writing;
reading comprehension assessment; learning analytics; intelligent tutoring;
peer assessment; citation analysis; science of science; open peer review
""".replace("\n", " ")

POOL = [t.strip() for t in TOPICS.split(";") if t.strip()]

FIRST_NAMES = [
    "Ana",
    "Bo",
    "Cyra",
    "Dev",
    "Elin",
    "Farouk",
    "Gia",
    "Hugo",
    "Ines",
    "Jun",
    "Kofi",
    "Lena",
    "Mateo",
    "Nia",
    "Oren",
    "Priya",
    "Quinn",
    "Rosa",
    "Sami",
    "Tove",
    "Umar",
    "Vera",
    "Wen",
    "Xavi",
    "Yara",
    "Zeno",
]
CHANNELS = ["methods", "general", "reading-group"]
DATASETS = [
    "Lagos air",
    "Baltic tide",
    "Kestrel scan",
    "Harbour sensor",
    "Mesa survey",
    "Orchid cohort",
    "Pine ridge",
    "Quarry audio",
    "Delta rainfall",
    "Fjord sonar",
    "Summit gait",
    "Atlas clinic",
    "Birch corpus",
    "Cedar trial",
    "Dune camera",
    "Ember lab",
    "Flint archive",
    "Grove soil",
]

#: What deliberation should decide for each kind of plant.
EXPECTED = {
    "emerging": "suggest",
    "one_off": "ignore",
    "colleague": "ignore",
    "capability": "capability",
    "learning": "suggest",
    "rejected": "ignore",
    "declared": "ignore",
    "told_fact": "record",
}
#: Plants whose topic must never be suggested (the false-suggestion check).
NEVER_SUGGEST = {"one_off", "colleague", "rejected", "declared"}

#: How the model is told to say each plant. ``{t}`` is the topic phrase.
GIST = {
    "emerging": "says in their own words that they would really like to dig into {t} themselves",  # noqa: E501
    "one_off": "mentions in passing that {t} came up somewhere and seemed mildly interesting",  # noqa: E501
    "colleague": "talks about {c}'s idea of using {t} (it is {c}'s idea, not their own interest)",  # noqa: E501
    "capability": "says they themselves ran or built something with {t} (e.g. 'I ran {t} on ...')",  # noqa: E501
    "learning": "says they want to learn {t} but do not know it yet",
    "rejected_maybe": "says they would like to try {t} on their work",
    "rejected_no": "says they have decided against {t} and will not do it after all",
    "declared": "says how much they enjoy working on {t}",
    "told_fact": "tells Mylo directly that the {t} for the {p} project has arrived",
}


@dataclass
class Plant:
    id: str
    person: str  # username
    kind: str  # a key of EXPECTED
    topic: str
    gist_key: str
    day: int  # days ago
    place: str  # channel name, or "dm"
    colleague: str = ""
    project: str = ""
    #: The mention of a two-part plant ("rejected"): 0 the maybe, 1 the no.
    part: int = 0


@dataclass
class Person:
    username: str
    name: str
    lab: str
    snowflake: str
    opted_in: bool = True
    declared: list[str] = field(default_factory=list)
    full_clusters: bool = False


@dataclass
class Lab:
    slug: str
    name: str
    guild: str
    projects: list[str]
    people: list[Person]


@dataclass
class World:
    seed: int
    labs: list[Lab]
    plants: list[Plant]

    def as_dict(self) -> dict:
        return asdict(self)

    def person(self, username: str) -> Person:
        for lab in self.labs:
            for person in lab.people:
                if person.username == username:
                    return person
        raise KeyError(username)


def build(
    seed: int = 20260919, *, labs: int = 3, people: int = 6, days: int = 26
) -> World:
    rng = random.Random(seed)
    topics = POOL[:]
    rng.shuffle(topics)
    names = FIRST_NAMES[:]
    rng.shuffle(names)
    datasets = DATASETS[:]
    rng.shuffle(datasets)
    out_labs: list[Lab] = []
    plants: list[Plant] = []
    counter = 0

    def pid() -> str:
        nonlocal counter
        counter += 1
        return f"p{counter}"

    for index in range(labs):
        letter = "abc"[index]
        lab_people: list[Person] = []
        for i in range(people + 1):
            name = names.pop()
            lab_people.append(
                Person(
                    username=f"amb_{letter}{i}_{name.lower()}",
                    name=name,
                    lab=f"amb-{letter}",
                    snowflake=f"9{index + 1}{i:03d}{seed % 1000:03d}",
                    opted_in=i < people,
                    declared=[topics.pop(), topics.pop()],
                    full_clusters=(i == 0),
                )
            )
        projects = [f"Project {letter.upper()}{n}" for n in (1, 2)]
        lab = Lab(
            slug=f"amb-{letter}",
            name=f"Ambient Sandbox Lab {letter.upper()}",
            guild=f"88{index + 1}{seed % 1000:03d}",
            projects=projects,
            people=lab_people,
        )
        out_labs.append(lab)
        speakers = [p for p in lab_people if p.opted_in]
        for person in speakers:
            others = [p for p in speakers if p is not person]

            def spread(n: int, gap: int = 5) -> list[int]:
                # n distinct days, first and last at least ``gap`` * (n-1) apart
                start = rng.randint((gap + 3) * (n - 1) + 1, days)
                return [start - k * rng.randint(gap, gap + 3) for k in range(n)]

            def place() -> str:
                return rng.choice(CHANNELS)

            emerging = topics.pop()
            for day in spread(3):
                plants.append(
                    Plant(
                        pid(),
                        person.username,
                        "emerging",
                        emerging,
                        "emerging",
                        max(1, day),
                        place(),
                    )
                )
            plants.append(
                Plant(
                    pid(),
                    person.username,
                    "one_off",
                    topics.pop(),
                    "one_off",
                    rng.randint(1, days),
                    place(),
                )
            )
            colleague_topic = topics.pop()
            colleague = rng.choice(others).name
            for day in spread(2):
                plants.append(
                    Plant(
                        pid(),
                        person.username,
                        "colleague",
                        colleague_topic,
                        "colleague",
                        max(1, day),
                        place(),
                        colleague=colleague,
                    )
                )
            capability = topics.pop()
            for day in spread(2):
                plants.append(
                    Plant(
                        pid(),
                        person.username,
                        "capability",
                        capability,
                        "capability",
                        max(1, day),
                        place(),
                    )
                )
            learning = topics.pop()
            for day in spread(2):
                plants.append(
                    Plant(
                        pid(),
                        person.username,
                        "learning",
                        learning,
                        "learning",
                        max(1, day),
                        place(),
                    )
                )
            rejected = topics.pop()
            first = rng.randint(14, days)
            for k, day in enumerate((first, first - 6, first - 11)):
                plants.append(
                    Plant(
                        pid(),
                        person.username,
                        "rejected",
                        rejected,
                        "rejected_no" if k == 2 else "rejected_maybe",
                        max(1, day),
                        place(),
                        part=1 if k == 2 else 0,
                    )
                )
            declared = person.declared[0]
            for day in spread(2):
                plants.append(
                    Plant(
                        pid(),
                        person.username,
                        "declared",
                        declared,
                        "declared",
                        max(1, day),
                        place(),
                    )
                )
            dataset = f"{datasets.pop() if datasets else 'Spare'} dataset"
            plants.append(
                Plant(
                    pid(),
                    person.username,
                    "told_fact",
                    dataset,
                    "told_fact",
                    rng.randint(1, 10),
                    "dm",
                    project=rng.choice(projects),
                )
            )
    return World(seed=seed, labs=out_labs, plants=plants)


def conversations(world: World, *, max_plants: int = 4) -> list[dict]:
    """Group plants into conversations: one per (lab, day, place), split so no
    conversation carries more than ``max_plants``. DMs are per person."""
    by_key: dict[tuple, list[Plant]] = {}
    lab_of = {p.username: lab.slug for lab in world.labs for p in lab.people}
    for plant in world.plants:
        if plant.place == "dm":
            key = (lab_of[plant.person], plant.day, "dm", plant.person)
        else:
            key = (lab_of[plant.person], plant.day, plant.place, "")
        by_key.setdefault(key, []).append(plant)
    out = []
    for (lab, day, place, dm_person), plants in sorted(by_key.items()):
        # A person's two mentions of one topic on one day would be one
        # conversation's worth anyway; keep chunks small for the model.
        for start in range(0, len(plants), max_plants):
            chunk = plants[start : start + max_plants]
            out.append(
                {
                    "id": f"{lab}:{day}:{place}:{dm_person or start}",
                    "lab": lab,
                    "day": day,
                    "place": place,
                    "dm_person": dm_person,
                    "plants": [p.id for p in chunk],
                }
            )
    return out
