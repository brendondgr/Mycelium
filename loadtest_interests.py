"""Static interest catalog + deterministic near-uniform selector for the load test.

This module holds a hand-written catalog of research interests spanning a wide
range of fields. It is intentionally *deterministic* data (no LLM, no network):
the load test builds each fake user's research profile from a small random
selection of these interests, so the interest distribution across users is broad
and reproducible for a given seed.

Each entry is an :class:`Interest` with:

- ``field``       — the broad discipline (used to keep the mix diverse).
- ``area``        — a concise research area label (becomes a profile "area").
- ``description`` — a 1–2 sentence statement (becomes profile statement text).
- ``keywords``    — a few semantic keywords (become profile keywords).

:func:`build_selector` returns a callable that deals interests from a reshuffled
"deck", which gives near-uniform coverage across users — far flatter than
independent random draws, which clump. The caller passes a seeded ``random.Random``
so a run is fully reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Interest:
    """One catalog interest: a field, an area, a statement, and keywords."""

    field: str
    area: str
    description: str
    keywords: tuple[str, ...]


# Raw catalog rows: (field, area, description, [keywords]). Kept as tuples for
# compactness; frozen into Interest objects below. ~24 fields x 6 = broad mix.
_RAW: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # --- Artificial Intelligence ---------------------------------------------
    ("Artificial Intelligence", "Large language model alignment",
     "Studying how to make large language models follow human intent safely, "
     "including reward modeling and evaluation of deceptive behavior.",
     ("alignment", "rlhf", "evaluation")),
    ("Artificial Intelligence", "Multi-agent reinforcement learning",
     "Investigating how populations of learning agents coordinate, compete, and "
     "converge in shared environments.",
     ("reinforcement learning", "game theory", "emergence")),
    ("Artificial Intelligence", "Retrieval-augmented generation",
     "Grounding generative models in external corpora to reduce hallucination "
     "and keep answers current.",
     ("retrieval", "RAG", "grounding")),
    ("Artificial Intelligence", "Vision-language models",
     "Building models that jointly reason over images and text for captioning, "
     "grounding, and visual question answering.",
     ("multimodal", "captioning", "grounding")),
    ("Artificial Intelligence", "Mechanistic interpretability",
     "Reverse-engineering the internal circuits of neural networks to explain "
     "how specific computations arise.",
     ("interpretability", "circuits", "features")),
    ("Artificial Intelligence", "Neural program synthesis",
     "Learning to generate correct programs from specifications or examples "
     "using search guided by neural models.",
     ("program synthesis", "code generation", "search")),
    # --- Machine Learning Theory ---------------------------------------------
    ("Machine Learning Theory", "Generalization bounds",
     "Deriving guarantees on how well over-parameterized models generalize "
     "beyond their training data.",
     ("generalization", "PAC learning", "over-parameterization")),
    ("Machine Learning Theory", "Optimization landscapes",
     "Characterizing the loss surfaces of deep networks and why gradient methods "
     "find good minima.",
     ("non-convex", "SGD", "loss landscape")),
    ("Machine Learning Theory", "Diffusion model sampling",
     "Analyzing the score-based dynamics that let diffusion models sample from "
     "complex distributions.",
     ("diffusion", "score matching", "sampling")),
    ("Machine Learning Theory", "Causal representation learning",
     "Recovering latent causal variables from observational data so models "
     "transfer under distribution shift.",
     ("causality", "latent variables", "invariance")),
    ("Machine Learning Theory", "Federated and private learning",
     "Training shared models across devices without centralizing data, with "
     "differential-privacy guarantees.",
     ("federated learning", "differential privacy", "distributed")),
    ("Machine Learning Theory", "Graph neural networks",
     "Studying expressive power and oversmoothing in message-passing networks "
     "over relational data.",
     ("graph learning", "message passing", "expressivity")),
    # --- Biomedicine ----------------------------------------------------------
    ("Biomedicine", "Cancer immunotherapy",
     "Engineering T-cell responses and checkpoint modulation to help the immune "
     "system recognize and clear tumors.",
     ("immunotherapy", "CAR-T", "checkpoint")),
    ("Biomedicine", "mRNA vaccine platforms",
     "Designing lipid-nanoparticle-delivered mRNA constructs for rapid vaccine "
     "and therapeutic development.",
     ("mRNA", "vaccines", "nanoparticles")),
    ("Biomedicine", "Antimicrobial resistance",
     "Tracking the evolution of drug-resistant pathogens and discovering new "
     "antibiotic mechanisms of action.",
     ("antibiotics", "resistance", "pathogens")),
    ("Biomedicine", "Organoid disease models",
     "Growing patient-derived organoids to model disease progression and screen "
     "candidate therapies ex vivo.",
     ("organoids", "disease models", "screening")),
    ("Biomedicine", "Neurodegeneration mechanisms",
     "Unraveling protein-misfolding and inflammation pathways that drive "
     "Alzheimer's and Parkinson's disease.",
     ("neurodegeneration", "protein folding", "inflammation")),
    ("Biomedicine", "Metabolic disease and the microbiome",
     "Linking gut-microbial metabolism to insulin resistance, obesity, and "
     "inflammatory conditions.",
     ("microbiome", "metabolism", "insulin resistance")),
    # --- Chemistry ------------------------------------------------------------
    ("Chemistry", "Catalysis for green chemistry",
     "Designing catalysts that make industrial reactions cleaner and more "
     "energy-efficient.",
     ("catalysis", "green chemistry", "reaction design")),
    ("Chemistry", "Metal-organic frameworks",
     "Building porous crystalline materials for gas storage, separation, and "
     "carbon capture.",
     ("MOFs", "porous materials", "carbon capture")),
    ("Chemistry", "Single-molecule spectroscopy",
     "Probing chemical dynamics one molecule at a time to reveal heterogeneity "
     "hidden in bulk measurements.",
     ("spectroscopy", "single-molecule", "dynamics")),
    ("Chemistry", "Electrochemical energy storage",
     "Developing electrode chemistries for next-generation batteries with higher "
     "density and longer life.",
     ("batteries", "electrochemistry", "electrodes")),
    ("Chemistry", "Computational drug design",
     "Using quantum chemistry and docking simulations to predict binding of "
     "small molecules to protein targets.",
     ("drug design", "docking", "quantum chemistry")),
    ("Chemistry", "Polymer self-assembly",
     "Directing block copolymers to self-organize into nanoscale patterns for "
     "membranes and coatings.",
     ("polymers", "self-assembly", "nanostructures")),
    # --- Physics --------------------------------------------------------------
    ("Physics", "Quantum error correction",
     "Designing fault-tolerant encodings that protect quantum information from "
     "decoherence and gate noise.",
     ("quantum computing", "error correction", "qubits")),
    ("Physics", "Topological phases of matter",
     "Classifying exotic states whose properties are protected by topology "
     "rather than symmetry alone.",
     ("topology", "condensed matter", "anyons")),
    ("Physics", "Gravitational-wave astronomy",
     "Extracting astrophysical signals from interferometer noise to study "
     "merging black holes and neutron stars.",
     ("gravitational waves", "interferometry", "black holes")),
    ("Physics", "Ultracold atomic gases",
     "Using laser-cooled atoms to simulate many-body quantum systems that are "
     "hard to model classically.",
     ("cold atoms", "quantum simulation", "BEC")),
    ("Physics", "High-energy collider phenomenology",
     "Searching collider data for signatures of physics beyond the Standard "
     "Model.",
     ("particle physics", "collider", "beyond standard model")),
    ("Physics", "Nonequilibrium statistical mechanics",
     "Understanding how driven systems dissipate energy and self-organize far "
     "from thermal equilibrium.",
     ("statistical mechanics", "nonequilibrium", "self-organization")),
    # --- Mathematics ----------------------------------------------------------
    ("Mathematics", "Analytic number theory",
     "Studying the distribution of primes and L-functions using tools from "
     "complex and harmonic analysis.",
     ("number theory", "primes", "L-functions")),
    ("Mathematics", "Low-dimensional topology",
     "Investigating knots, 3-manifolds, and the surprising rigidity of four "
     "dimensions.",
     ("topology", "manifolds", "knots")),
    ("Mathematics", "Optimal transport",
     "Developing the geometry of moving one distribution to another and its uses "
     "in analysis and learning.",
     ("optimal transport", "geometry", "measures")),
    ("Mathematics", "Stochastic partial differential equations",
     "Analyzing PDEs driven by noise to model turbulence, growth, and random "
     "interfaces.",
     ("SPDE", "probability", "analysis")),
    ("Mathematics", "Algebraic combinatorics",
     "Connecting combinatorial structures to representation theory and symmetric "
     "functions.",
     ("combinatorics", "representation theory", "symmetric functions")),
    ("Mathematics", "Arithmetic geometry",
     "Studying solutions to polynomial equations through the interplay of number "
     "theory and geometry.",
     ("arithmetic geometry", "elliptic curves", "Galois")),
    # --- Computer Systems -----------------------------------------------------
    ("Computer Systems", "Distributed consensus protocols",
     "Designing fault-tolerant agreement algorithms that keep replicated systems "
     "consistent under failure.",
     ("consensus", "replication", "fault tolerance")),
    ("Computer Systems", "Serverless and edge computing",
     "Scheduling ephemeral functions across edge locations to cut latency and "
     "cost for interactive apps.",
     ("serverless", "edge", "scheduling")),
    ("Computer Systems", "Compiler autotuning",
     "Learning code-transformation policies that adapt compilation to hardware "
     "and workload.",
     ("compilers", "autotuning", "optimization")),
    ("Computer Systems", "Memory-safe systems languages",
     "Advancing type systems and tooling that eliminate whole classes of memory "
     "bugs in low-level code.",
     ("memory safety", "type systems", "Rust")),
    ("Computer Systems", "Accelerator architecture for ML",
     "Co-designing chips and dataflows to run large neural networks efficiently.",
     ("accelerators", "dataflow", "hardware")),
    ("Computer Systems", "Formal verification of software",
     "Proving programs correct with respect to specifications using interactive "
     "and automated theorem provers.",
     ("verification", "proof assistants", "correctness")),
    # --- Neuroscience ---------------------------------------------------------
    ("Neuroscience", "Neural coding of decision-making",
     "Recording population activity to understand how the brain accumulates "
     "evidence and commits to choices.",
     ("decision-making", "neural coding", "electrophysiology")),
    ("Neuroscience", "Connectomics",
     "Reconstructing wiring diagrams of neural circuits from dense electron-"
     "microscopy volumes.",
     ("connectome", "circuits", "electron microscopy")),
    ("Neuroscience", "Computational models of memory",
     "Building models of how synaptic plasticity supports the formation and "
     "recall of memories.",
     ("memory", "plasticity", "hippocampus")),
    ("Neuroscience", "Brain-computer interfaces",
     "Decoding motor intent from cortical signals to restore movement and "
     "communication.",
     ("BCI", "decoding", "neuroprosthetics")),
    ("Neuroscience", "Neuroinflammation and glia",
     "Studying how microglia and astrocytes shape circuit health in development "
     "and disease.",
     ("glia", "microglia", "neuroinflammation")),
    ("Neuroscience", "Sensory perception and attention",
     "Mapping how the visual and auditory systems select and represent behaviorally "
     "relevant signals.",
     ("perception", "attention", "sensory systems")),
    # --- Economics ------------------------------------------------------------
    ("Economics", "Market design and matching",
     "Designing allocation mechanisms — for schools, organs, and spectrum — that "
     "are efficient and strategy-proof.",
     ("market design", "matching", "mechanism design")),
    ("Economics", "Causal inference in labor markets",
     "Using natural experiments to estimate how policies affect wages, employment, "
     "and inequality.",
     ("labor economics", "causal inference", "policy")),
    ("Economics", "Behavioral game theory",
     "Modeling how bounded rationality and social preferences shape strategic "
     "behavior.",
     ("behavioral economics", "game theory", "preferences")),
    ("Economics", "Macro-finance and monetary policy",
     "Studying how credit, expectations, and central-bank actions transmit to the "
     "real economy.",
     ("macroeconomics", "monetary policy", "finance")),
    ("Economics", "Development economics field experiments",
     "Running randomized trials to evaluate interventions in health, education, and "
     "credit access.",
     ("development", "RCT", "impact evaluation")),
    ("Economics", "Environmental and energy economics",
     "Pricing externalities and designing policies that steer investment toward "
     "low-carbon energy.",
     ("environmental economics", "carbon pricing", "energy")),
    # --- Sociology ------------------------------------------------------------
    ("Sociology", "Social network diffusion",
     "Modeling how information, norms, and behaviors spread through the structure "
     "of social ties.",
     ("networks", "diffusion", "social influence")),
    ("Sociology", "Urban inequality and segregation",
     "Examining how housing, policing, and mobility reproduce spatial inequality in "
     "cities.",
     ("inequality", "urban", "segregation")),
    ("Sociology", "Computational social science",
     "Using large digital-trace datasets to study collective behavior at scale.",
     ("computational social science", "big data", "collective behavior")),
    ("Sociology", "Sociology of work and automation",
     "Studying how technological change reshapes occupations, skills, and worker "
     "power.",
     ("work", "automation", "labor")),
    ("Sociology", "Migration and belonging",
     "Investigating how migrants build identity and community across borders.",
     ("migration", "identity", "community")),
    ("Sociology", "Education and social mobility",
     "Analyzing how schooling systems widen or narrow opportunity across "
     "generations.",
     ("education", "mobility", "stratification")),
    # --- Linguistics ----------------------------------------------------------
    ("Linguistics", "Computational syntax",
     "Building formal grammars and parsers that capture the structure of human "
     "language.",
     ("syntax", "grammar", "parsing")),
    ("Linguistics", "Language documentation",
     "Recording and analyzing endangered languages to preserve linguistic "
     "diversity.",
     ("documentation", "endangered languages", "fieldwork")),
    ("Linguistics", "Psycholinguistics of comprehension",
     "Measuring how readers and listeners build meaning in real time.",
     ("psycholinguistics", "comprehension", "processing")),
    ("Linguistics", "Sociolinguistic variation",
     "Studying how pronunciation and grammar vary with region, class, and identity.",
     ("sociolinguistics", "variation", "dialects")),
    ("Linguistics", "Semantics and pragmatics",
     "Formalizing how context shapes literal meaning and implicature.",
     ("semantics", "pragmatics", "meaning")),
    ("Linguistics", "Phonological typology",
     "Comparing sound systems across languages to find universal and rare "
     "patterns.",
     ("phonology", "typology", "sound systems")),
    # --- Ecology & Evolution --------------------------------------------------
    ("Ecology & Evolution", "Biodiversity under climate change",
     "Predicting how species ranges and communities shift as the climate warms.",
     ("biodiversity", "climate", "species distribution")),
    ("Ecology & Evolution", "Microbial community ecology",
     "Understanding how microbial consortia assemble and provide ecosystem "
     "functions.",
     ("microbial ecology", "community", "ecosystem function")),
    ("Ecology & Evolution", "Evolution of cooperation",
     "Explaining how altruistic behavior persists despite selection for "
     "self-interest.",
     ("cooperation", "evolution", "kin selection")),
    ("Ecology & Evolution", "Landscape and movement ecology",
     "Tracking animal movement to link individual behavior to population "
     "dynamics.",
     ("movement ecology", "tracking", "landscape")),
    ("Ecology & Evolution", "Coral reef resilience",
     "Studying how reef ecosystems resist and recover from bleaching and "
     "acidification.",
     ("coral reefs", "resilience", "bleaching")),
    ("Ecology & Evolution", "Phylogenomics",
     "Reconstructing the tree of life from genome-scale data to date "
     "diversification.",
     ("phylogenomics", "tree of life", "diversification")),
    # --- Climate Science ------------------------------------------------------
    ("Climate Science", "Cloud feedbacks in climate models",
     "Reducing uncertainty in how clouds amplify or dampen global warming.",
     ("clouds", "feedbacks", "climate models")),
    ("Climate Science", "Ice-sheet dynamics",
     "Modeling how polar ice sheets flow and contribute to sea-level rise.",
     ("ice sheets", "sea level", "glaciology")),
    ("Climate Science", "Extreme-event attribution",
     "Quantifying how much climate change altered the odds of a specific heatwave "
     "or flood.",
     ("extreme events", "attribution", "risk")),
    ("Climate Science", "Carbon-cycle feedbacks",
     "Tracking how land and ocean carbon sinks respond to a warming world.",
     ("carbon cycle", "sinks", "feedbacks")),
    ("Climate Science", "Regional climate downscaling",
     "Translating global projections into actionable local forecasts.",
     ("downscaling", "regional climate", "projections")),
    ("Climate Science", "Atmospheric aerosols",
     "Measuring how aerosols scatter light and seed clouds, shaping radiative "
     "balance.",
     ("aerosols", "radiation", "air quality")),
    # --- Materials Science ----------------------------------------------------
    ("Materials Science", "2D materials beyond graphene",
     "Exploring atomically thin semiconductors for flexible and optoelectronic "
     "devices.",
     ("2D materials", "semiconductors", "optoelectronics")),
    ("Materials Science", "High-entropy alloys",
     "Designing multi-element alloys with unusual strength and corrosion "
     "resistance.",
     ("alloys", "high-entropy", "metallurgy")),
    ("Materials Science", "Solid-state electrolytes",
     "Developing ceramic conductors that make solid-state batteries safe and "
     "dense.",
     ("solid-state", "electrolytes", "batteries")),
    ("Materials Science", "Machine-learning interatomic potentials",
     "Training fast surrogate models of quantum forces to simulate materials at "
     "scale.",
     ("interatomic potentials", "simulation", "DFT")),
    ("Materials Science", "Photovoltaic perovskites",
     "Improving the stability and efficiency of perovskite solar absorbers.",
     ("perovskites", "solar cells", "photovoltaics")),
    ("Materials Science", "Additive manufacturing metallurgy",
     "Controlling microstructure during 3D printing of metal parts.",
     ("additive manufacturing", "3D printing", "microstructure")),
    # --- Astronomy & Astrophysics --------------------------------------------
    ("Astronomy & Astrophysics", "Exoplanet atmospheres",
     "Characterizing distant planets' atmospheres through transit spectroscopy.",
     ("exoplanets", "spectroscopy", "atmospheres")),
    ("Astronomy & Astrophysics", "Galaxy formation and evolution",
     "Tracing how galaxies assemble their stars and black holes over cosmic time.",
     ("galaxies", "star formation", "cosmology")),
    ("Astronomy & Astrophysics", "Cosmic microwave background",
     "Mining relic radiation for clues about the early universe and inflation.",
     ("CMB", "inflation", "early universe")),
    ("Astronomy & Astrophysics", "Time-domain and transient astronomy",
     "Catching supernovae and tidal-disruption events across rapid all-sky "
     "surveys.",
     ("transients", "supernovae", "surveys")),
    ("Astronomy & Astrophysics", "Dark matter detection",
     "Searching for weakly interacting particles that dominate the mass of the "
     "cosmos.",
     ("dark matter", "detectors", "particle astrophysics")),
    ("Astronomy & Astrophysics", "Stellar nucleosynthesis",
     "Modeling how stars forge the chemical elements and seed galaxies.",
     ("nucleosynthesis", "stellar evolution", "abundances")),
    # --- Genetics & Genomics --------------------------------------------------
    ("Genetics & Genomics", "CRISPR gene editing",
     "Refining precision editors that correct disease-causing mutations with few "
     "off-target effects.",
     ("CRISPR", "gene editing", "base editing")),
    ("Genetics & Genomics", "Single-cell transcriptomics",
     "Profiling gene expression cell by cell to map tissue heterogeneity and "
     "lineage.",
     ("single-cell", "transcriptomics", "lineage")),
    ("Genetics & Genomics", "Population genomics",
     "Using genome-wide variation to reconstruct history, selection, and disease "
     "risk.",
     ("population genomics", "selection", "GWAS")),
    ("Genetics & Genomics", "Epigenetic regulation",
     "Studying how chromatin marks control gene expression without changing DNA "
     "sequence.",
     ("epigenetics", "chromatin", "gene regulation")),
    ("Genetics & Genomics", "Long-read genome assembly",
     "Completing complex genomic regions with long-read sequencing technology.",
     ("long reads", "assembly", "sequencing")),
    ("Genetics & Genomics", "Synthetic biology circuits",
     "Engineering genetic circuits that make cells sense, compute, and respond.",
     ("synthetic biology", "genetic circuits", "biosensors")),
    # --- Robotics -------------------------------------------------------------
    ("Robotics", "Dexterous manipulation",
     "Teaching robot hands to grasp and manipulate unfamiliar objects robustly.",
     ("manipulation", "grasping", "control")),
    ("Robotics", "Legged locomotion",
     "Developing controllers that let legged robots traverse rough, unstructured "
     "terrain.",
     ("legged robots", "locomotion", "control")),
    ("Robotics", "Robot learning from demonstration",
     "Letting robots acquire skills by imitating human demonstrations.",
     ("imitation learning", "demonstration", "skills")),
    ("Robotics", "Swarm robotics",
     "Coordinating many simple robots to achieve collective tasks without central "
     "control.",
     ("swarm", "collective", "decentralized")),
    ("Robotics", "Soft robotics",
     "Building compliant robots from soft materials for safe interaction and "
     "delicate handling.",
     ("soft robotics", "compliant", "actuators")),
    ("Robotics", "Aerial autonomy",
     "Enabling drones to plan and fly safely in cluttered, GPS-denied "
     "environments.",
     ("drones", "autonomy", "planning")),
    # --- Philosophy -----------------------------------------------------------
    ("Philosophy", "Ethics of artificial intelligence",
     "Examining moral responsibility, fairness, and agency as decisions are "
     "delegated to machines.",
     ("AI ethics", "responsibility", "fairness")),
    ("Philosophy", "Philosophy of mind and consciousness",
     "Debating what consciousness is and whether it can be explained "
     "physically.",
     ("consciousness", "mind", "qualia")),
    ("Philosophy", "Formal epistemology",
     "Using logic and probability to model rational belief and evidence.",
     ("epistemology", "probability", "rationality")),
    ("Philosophy", "Political philosophy of justice",
     "Analyzing competing theories of fairness in the distribution of goods and "
     "power.",
     ("justice", "political philosophy", "distribution")),
    ("Philosophy", "Philosophy of science",
     "Investigating what makes explanation, causation, and scientific inference "
     "work.",
     ("explanation", "causation", "inference")),
    ("Philosophy", "Metaethics of moral realism",
     "Asking whether moral facts exist independently of what anyone believes.",
     ("metaethics", "moral realism", "value")),
    # --- Psychology -----------------------------------------------------------
    ("Psychology", "Cognitive development in children",
     "Charting how reasoning, language, and social understanding emerge in early "
     "childhood.",
     ("development", "cognition", "children")),
    ("Psychology", "Judgment and decision-making",
     "Studying the heuristics and biases that shape everyday choices under "
     "uncertainty.",
     ("decision-making", "heuristics", "bias")),
    ("Psychology", "Clinical models of anxiety and depression",
     "Testing cognitive and neural mechanisms behind mood disorders and their "
     "treatment.",
     ("clinical psychology", "depression", "anxiety")),
    ("Psychology", "Social psychology of cooperation",
     "Understanding trust, fairness, and group identity in human interaction.",
     ("social psychology", "trust", "cooperation")),
    ("Psychology", "Memory and learning",
     "Investigating how experiences are encoded, consolidated, and retrieved.",
     ("memory", "learning", "consolidation")),
    ("Psychology", "Quantitative and psychometric methods",
     "Improving how psychological constructs are measured and modeled "
     "statistically.",
     ("psychometrics", "measurement", "statistics")),
    # --- Political Science ----------------------------------------------------
    ("Political Science", "Comparative democratization",
     "Explaining why some countries build durable democracies while others "
     "backslide.",
     ("democratization", "regimes", "comparative")),
    ("Political Science", "Political economy of institutions",
     "Studying how rules and organizations shape economic and political "
     "outcomes.",
     ("institutions", "political economy", "governance")),
    ("Political Science", "Conflict and peacebuilding",
     "Analyzing the causes of civil conflict and what makes peace agreements "
     "last.",
     ("conflict", "peacebuilding", "security")),
    ("Political Science", "Public opinion and polarization",
     "Measuring how identities and media shape attitudes and partisan divides.",
     ("public opinion", "polarization", "media")),
    ("Political Science", "International cooperation",
     "Examining when states cooperate through treaties and institutions on shared "
     "problems.",
     ("international relations", "cooperation", "treaties")),
    ("Political Science", "Electoral systems and representation",
     "Comparing how voting rules translate preferences into representation.",
     ("elections", "representation", "voting")),
    # --- Public Health & Epidemiology ----------------------------------------
    ("Public Health & Epidemiology", "Infectious-disease modeling",
     "Building transmission models to forecast epidemics and evaluate "
     "interventions.",
     ("epidemiology", "transmission", "forecasting")),
    ("Public Health & Epidemiology", "Health disparities",
     "Investigating how social determinants drive unequal health outcomes across "
     "populations.",
     ("disparities", "social determinants", "equity")),
    ("Public Health & Epidemiology", "Environmental health exposures",
     "Linking air, water, and chemical exposures to long-term health effects.",
     ("exposures", "environmental health", "pollution")),
    ("Public Health & Epidemiology", "Vaccine hesitancy and uptake",
     "Understanding the behavioral drivers of immunization decisions.",
     ("vaccines", "behavior", "uptake")),
    ("Public Health & Epidemiology", "Global maternal and child health",
     "Improving outcomes for mothers and infants in low-resource settings.",
     ("maternal health", "global health", "child health")),
    ("Public Health & Epidemiology", "Wastewater-based surveillance",
     "Monitoring pathogens and drugs in sewage to track community-level trends.",
     ("surveillance", "wastewater", "pathogens")),
    # --- Art History ----------------------------------------------------------
    ("Art History", "Renaissance patronage networks",
     "Tracing how patrons, workshops, and markets shaped Renaissance art "
     "production.",
     ("Renaissance", "patronage", "workshops")),
    ("Art History", "Digital art history",
     "Applying computational imaging and network analysis to study visual "
     "corpora.",
     ("digital humanities", "imaging", "corpora")),
    ("Art History", "Postcolonial visual culture",
     "Examining how empire and its aftermath shaped image-making and display.",
     ("postcolonial", "visual culture", "empire")),
    ("Art History", "Conservation science",
     "Using material analysis to understand and preserve paintings and "
     "artifacts.",
     ("conservation", "materials", "preservation")),
    ("Art History", "Modernism and the avant-garde",
     "Studying how early-twentieth-century movements redefined art and "
     "abstraction.",
     ("modernism", "avant-garde", "abstraction")),
    ("Art History", "Iconography and symbolism",
     "Decoding recurring visual symbols and their shifting meanings across "
     "periods.",
     ("iconography", "symbolism", "interpretation")),
    # --- Music & Sound --------------------------------------------------------
    ("Music & Sound", "Music information retrieval",
     "Extracting structure, genre, and mood from audio for search and "
     "recommendation.",
     ("MIR", "audio", "retrieval")),
    ("Music & Sound", "Computational musicology",
     "Analyzing large score corpora to study style, influence, and change over "
     "time.",
     ("musicology", "corpus", "style")),
    ("Music & Sound", "Psychoacoustics",
     "Studying how the ear and brain perceive pitch, timbre, and loudness.",
     ("psychoacoustics", "perception", "hearing")),
    ("Music & Sound", "Neural audio synthesis",
     "Generating and transforming sound with deep generative models.",
     ("audio synthesis", "generative", "sound")),
    ("Music & Sound", "Ethnomusicology of oral traditions",
     "Documenting and analyzing music transmitted without notation across "
     "cultures.",
     ("ethnomusicology", "oral tradition", "culture")),
    ("Music & Sound", "Acoustics of performance spaces",
     "Modeling how architecture shapes the sound of concert halls and rooms.",
     ("acoustics", "reverberation", "architecture")),
    # --- Science, Technology & Education --------------------------------------
    ("Science, Technology & Education", "Learning analytics",
     "Using data from digital learning to understand and support how students "
     "learn.",
     ("learning analytics", "education data", "assessment")),
    ("Science, Technology & Education", "Science communication",
     "Studying how expert knowledge is translated for and trusted by the "
     "public.",
     ("science communication", "trust", "public understanding")),
    ("Science, Technology & Education", "Human-computer interaction",
     "Designing and evaluating interfaces that fit how people think and work.",
     ("HCI", "usability", "interaction design")),
    ("Science, Technology & Education", "Research reproducibility",
     "Developing methods and incentives that make scientific findings more "
     "replicable.",
     ("reproducibility", "open science", "methods")),
    ("Science, Technology & Education", "History and sociology of technology",
     "Examining how technologies and societies co-evolve over time.",
     ("STS", "technology", "society")),
    ("Science, Technology & Education", "Ethics of data and privacy",
     "Analyzing consent, surveillance, and fairness in data-driven systems.",
     ("data ethics", "privacy", "surveillance")),
)


CATALOG: tuple[Interest, ...] = tuple(
    Interest(field=field, area=area, description=desc, keywords=tuple(kws))
    for field, area, desc, kws in _RAW
)

#: The distinct fields represented, for reporting the interest spread.
FIELDS: tuple[str, ...] = tuple(dict.fromkeys(i.field for i in CATALOG))


def build_selector(
    rng: random.Random,
    *,
    min_per_user: int = 2,
    max_per_user: int = 3,
) -> Callable[[], list[Interest]]:
    """Return a callable that deals ``min..max`` distinct interests per user.

    Interests are dealt from a reshuffled deck of the whole catalog, so coverage
    stays near-uniform across many users instead of clumping the way independent
    ``random.sample`` draws do. ``rng`` is a seeded ``random.Random`` for
    reproducibility; the returned callable is not thread-safe (the harness is
    single-threaded asyncio, so that is fine).
    """
    if min_per_user < 1 or max_per_user < min_per_user:
        raise ValueError("need 1 <= min_per_user <= max_per_user")
    if max_per_user > len(CATALOG):
        raise ValueError("max_per_user exceeds catalog size")

    deck: list[Interest] = []

    def _refill() -> None:
        fresh = list(CATALOG)
        rng.shuffle(fresh)
        deck.extend(fresh)

    def deal() -> list[Interest]:
        count = rng.randint(min_per_user, max_per_user)
        if len(deck) < count:
            _refill()
        picked: list[Interest] = []
        seen_areas: set[str] = set()
        # Pull from the front of the deck, skipping a same-area duplicate within
        # this one user (rare, only when the deck wraps mid-deal).
        while len(picked) < count and deck:
            interest = deck.pop(0)
            if interest.area in seen_areas:
                deck.append(interest)  # defer; try the next card
                # Guard against an all-duplicate tail by refilling if needed.
                if all(i.area in seen_areas for i in deck):
                    _refill()
                continue
            picked.append(interest)
            seen_areas.add(interest.area)
        return picked

    return deal


if __name__ == "__main__":  # pragma: no cover - manual sanity check
    import collections

    print(f"catalog: {len(CATALOG)} interests across {len(FIELDS)} fields")
    r = random.Random(7)
    pick = build_selector(r)
    counter: collections.Counter[str] = collections.Counter()
    for _ in range(500):
        for interest in pick():
            counter[interest.field] += 1
    spread = ", ".join(f"{field}={n}" for field, n in counter.most_common())
    print("field spread over 500 users:")
    print(" ", spread)
