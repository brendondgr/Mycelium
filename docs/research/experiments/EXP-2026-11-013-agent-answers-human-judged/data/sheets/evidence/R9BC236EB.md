# R9BC236EB

## Question

Does this paper change anything for the Marine heatwave early warning project, and who on the team should read it?

## Answer

Here's what I can tell you:

**What the paper is**

#1 is a 2026 B.S. thesis (University of Dhaka, Dept. of Meteorology) by Abu Baser Mojumder, deposited on Zenodo. It evaluates 1–14-day machine-learning forecasts of marine heatwaves in the Northern Bay of Bengal, benchmarked against persistence. The abstract is thin — it's essentially the code, processed data, and results of the thesis as submitted. I don't have the full text stored, so I can't speak to the specific ML architecture, skill scores, or failure modes beyond what the title and abstract say.

**Does it change anything for the project?**

It's already on the project's slate (#8) as a new entry since 11 Nov, so Mycelium's ranking has flagged it as relevant. In substance, it's a useful **benchmarking reference** for the early-warning project: a recent, independent evaluation of ML-based MHW forecasts at sub-monthly lead times, explicitly compared against a persistence baseline. That's the kind of comparison you'd want to mirror or cite when justifying that ML forecasts add skill over "do nothing" forecasts. It's a student thesis, so the methods and evaluation are likely straightforward rather than novel — but the Bay of Bengal setting and the explicit persistence benchmark make it a concrete, citable data point.

I can't say it changes the project's direction or method; it's more of a supporting reference. If you can share the full text (or a PDF), I can dig into the specific skill metrics and whether they'd strengthen or complicate your evaluation story.

**Who on the team should read it**

The project has three members:

- **You (Mara Ellison)** — as PI and owner, you should at least skim it to decide whether it earns a citation in your methods or related-work section.
- **Tomás Ferreira-Lind** — declared interest in physics-informed ML; he's the person most likely to assess whether the ML approach and benchmarking are sound and worth adopting.
- **Sun-hee Park** — declared interest in ocean data tools; the practical evaluation setup (data, code, persistence baseline) is squarely in her wheelhouse.

The other two lab members (Jonah, Priya) are on the Plastic pathways project and don't have declared interests that overlap here, so I wouldn't flag it for them.

Want me to try to pull the full text so we can look at the actual skill numbers?

## Evidence

### Reference numbers in this conversation

- #1: [paper] Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
- #2: Coastal Ocean Intelligence Lab
- #3: Mara Ellison (@demo.mara)
- #4: Jonah Whitcombe (@demo.jonah)
- #5: Priya Raman (@demo.priya)
- #6: Sun-hee Park (@demo.sunhee)
- #7: Tomás Ferreira-Lind (@demo.tomas)
- #8: Marine heatwave early warning
- #9: Plastic pathways
- #10: [conference] 10th International Conference on Geoinformatics and Data Analysis
- #11: [paper] Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish
- #12: [grant] Geosciences Research: Atmospheric, Geospace, Earth, and Ocean Sciences (GEO Core)
- #13: [fellowship] Woods Hole Oceanographic Institution (WHOI) - Geophysical Fluid Dynamics (GFD) Summer Graduate Research Fellowship
- #14: [paper] Rescene-ESM: an Earth system model built around a frozen AI weather model
- #15: [grant] Ocean Technology and Interdisciplinary Coordination
- #16: [paper] Daily Analyses of the Pacific Regional Ocean Forecast System model
- #17: [conference] 12th International Conference on Big Data Analytics
- #18: [fellowship] National Oceanic and Atmospheric Administration (NOAA) - Dr. Nancy Foster Scholarship Program

### Function result: corpus_item

#1 [paper] Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
Authors: Abu Baser Mojumder
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.24030524
Still open/current: yes
Problem (Mycelium's reading): Evaluation of 1-14-day machine-learning forecasts of marine heatwaves in the Northern Bay of Bengal against persistence benchmarks
Method (Mycelium's reading): Machine-learning forecasting evaluated against persistence benchmarks
Setting (Mycelium's reading): Northern Bay of Bengal
Abstract:
Code, processed data and results of the B.S. thesis "Evaluation of 1–14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks" (Department of Meteorology, University of Dhaka, 2026), as submitted.

### Function result: load_functions

Loaded: projects_get, org_lab_members. They are available from your next step.

### Function result: org_lab_members

Members of #2 Coastal Ocean Intelligence Lab (5):
- #3 Mara Ellison (@demo.mara) — owner, PI; declared interests: Data assimilation with ML, Ocean extremes
- #4 Jonah Whitcombe (@demo.jonah) — member; declared interests: Marine litter, Lagrangian analysis
- #5 Priya Raman (@demo.priya) — member; declared interests: Satellite oceanography, Coastal water quality
- #6 Sun-hee Park (@demo.sunhee) — member; declared interests: Ocean data tools
- #7 Tomás Ferreira-Lind (@demo.tomas) — member; declared interests: Circulation and turbulence, Physics-informed ML

### Function result: load_functions

Loaded: projects_list. They are available from your next step.

### Function result: projects_list

Projects:
- #8 Marine heatwave early warning — lab project, 3 members
- #9 Plastic pathways — lab project, 3 members

### Function result: projects_get

#8
Project: Marine heatwave early warning (scope: lab)
Members: Mara Ellison, Tomás Ferreira-Lind, Sun-hee Park

### Function result: load_functions

Loaded: projects_feed. They are available from your next step.

### Function result: projects_feed

Current slate of #8 Marine heatwave early warning, in rank order:
- #10 10th International Conference on Geoinformatics and Data Analysis [conference, in slate since 2026-11-10] — 10th International Conference on Geoinformatics and Data Analysis
- #11 Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish [paper, in slate since 2026-11-10] (new) — Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish
- #1 Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks [paper, in slate since 2026-11-10] (new) — Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
- #12 Geosciences Research: Atmospheric, Geospace, Earth, and Ocean Sciences (GEO Core) [grant, in slate since 2026-11-10] — Geosciences Research: Atmospheric, Geospace, Earth, and Ocean Sciences (GEO Core)
- #13 Woods Hole Oceanographic Institution (WHOI) - Geophysical Fluid Dynamics (GFD) Summer Graduate Research Fellowship [fellowship, in slate since 2026-11-10] — WHOI GFD Summer Fellowship
- #14 Rescene-ESM: an Earth system model built around a frozen AI weather model [paper, in slate since 2026-11-10] (new) — Rescene-ESM: an Earth system model built around a frozen AI weather model
- #15 Ocean Technology and Interdisciplinary Coordination [grant, in slate since 2026-11-10] — Ocean Technology and Interdisciplinary Coordination
- #16 Daily Analyses of the Pacific Regional Ocean Forecast System model [paper, in slate since 2026-11-10] (new) — Daily Analyses of the Pacific Regional Ocean Forecast System model
- #17 12th International Conference on Big Data Analytics [conference, in slate since 2026-11-10] — 12th International Conference on Big Data Analytics
- #18 National Oceanic and Atmospheric Administration (NOAA) - Dr. Nancy Foster Scholarship Program [fellowship, in slate since 2026-11-10] — NOAA Oceanography Scholarship

### Reference cards in view

#1 item: [paper] Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
   paper · Zenodo (CERN European Organization for Nuclear Research) · 2026
   read more: corpus_item(item='#1')
