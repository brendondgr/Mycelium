# RF7B0A86A

## Question

What is blocking the Marine heatwave early warning project, and is there a paper in our feed that could help with it?

## Answer

Here's where the **Marine heatwave early warning** project (#1) stands:

**Blockers:** None are currently recorded in the project's confirmed state. The project has three members (you, Tomás Ferreira-Lind, and Sun-hee Park), but no open blockers, milestones, or developments have been logged yet. If there's something holding the team up that isn't captured here, it would need to be added in the app — I can't edit the project myself.

**Papers in the feed that could help:**

Two new papers entered the slate this week (2026-11-10) that speak directly to the project:

- **#5 — "Evaluation of 1–14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks"** (Mojumder, 2026, Zenodo). This is the most directly useful one: it benchmarks ML-based MHW forecasts at 1–14 day lead times against persistence, which is exactly the forecasting skill an early-warning system needs to be trustworthy. It's a B.S. thesis with code and data available, so the team could pull the methods and benchmark setup to compare against their own approach.

- **#4 — "Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish"** (Stuart-Smith et al., 2026, *Conservation Science and Practice*). This one is more about the *response* side: a pre-emptive rescue of a threatened fish species triggered by a climate forecast ahead of an El Niño-driven MHW. It's a good example of how a forecast translates into a concrete, time-sensitive action — useful if the project's goal is to show that early warnings lead to real interventions, not just predictions.

If the team is stuck on a specific question — say, how to validate their ML forecasts, or how to frame the "so what" of a warning for managers — I can dig into either paper's full text. Just let me know which direction is most pressing.

## Evidence

### Reference numbers in this conversation

- #1: Marine heatwave early warning
- #2: Plastic pathways
- #3: [conference] 10th International Conference on Geoinformatics and Data Analysis
- #4: [paper] Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish
- #5: [paper] Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
- #6: [grant] Geosciences Research: Atmospheric, Geospace, Earth, and Ocean Sciences (GEO Core)
- #7: [fellowship] Woods Hole Oceanographic Institution (WHOI) - Geophysical Fluid Dynamics (GFD) Summer Graduate Research Fellowship
- #8: [paper] Rescene-ESM: an Earth system model built around a frozen AI weather model
- #9: [grant] Ocean Technology and Interdisciplinary Coordination
- #10: [paper] Daily Analyses of the Pacific Regional Ocean Forecast System model
- #11: [conference] 12th International Conference on Big Data Analytics
- #12: [fellowship] National Oceanic and Atmospheric Administration (NOAA) - Dr. Nancy Foster Scholarship Program

### Function result: read_skill

# Reviewing a project

1. `projects_get` for goals, confirmed state, blockers, milestones,
   developments in effect and members. Note when the state was last confirmed;
   past thirty days, say it may be out of date.
2. `projects_feed` for the current slate, in rank order, with when each item
   entered. "New this week" means it entered the slate this week.
3. Tie items to blockers: for each open blocker, which slate item (if any)
   speaks to it, and why. Cite both by #n.
4. End with what the team might do next, phrased as suggestions. You cannot
   change the project; point to the app for edits.

### Function result: load_functions

Loaded: projects_get, projects_feed. They are available from your next step.

### Function result: load_functions

Loaded: projects_list. They are available from your next step.

### Function result: projects_list

Projects:
- #1 Marine heatwave early warning — lab project, 3 members
- #2 Plastic pathways — lab project, 3 members

### Function result: projects_get

#1
Project: Marine heatwave early warning (scope: lab)
Members: Mara Ellison, Tomás Ferreira-Lind, Sun-hee Park

### Function result: projects_feed

Current slate of #1 Marine heatwave early warning, in rank order:
- #3 10th International Conference on Geoinformatics and Data Analysis [conference, in slate since 2026-11-10] — 10th International Conference on Geoinformatics and Data Analysis
- #4 Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish [paper, in slate since 2026-11-10] (new) — Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish
- #5 Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks [paper, in slate since 2026-11-10] (new) — Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
- #6 Geosciences Research: Atmospheric, Geospace, Earth, and Ocean Sciences (GEO Core) [grant, in slate since 2026-11-10] — Geosciences Research: Atmospheric, Geospace, Earth, and Ocean Sciences (GEO Core)
- #7 Woods Hole Oceanographic Institution (WHOI) - Geophysical Fluid Dynamics (GFD) Summer Graduate Research Fellowship [fellowship, in slate since 2026-11-10] — WHOI GFD Summer Fellowship
- #8 Rescene-ESM: an Earth system model built around a frozen AI weather model [paper, in slate since 2026-11-10] (new) — Rescene-ESM: an Earth system model built around a frozen AI weather model
- #9 Ocean Technology and Interdisciplinary Coordination [grant, in slate since 2026-11-10] — Ocean Technology and Interdisciplinary Coordination
- #10 Daily Analyses of the Pacific Regional Ocean Forecast System model [paper, in slate since 2026-11-10] (new) — Daily Analyses of the Pacific Regional Ocean Forecast System model
- #11 12th International Conference on Big Data Analytics [conference, in slate since 2026-11-10] — 12th International Conference on Big Data Analytics
- #12 National Oceanic and Atmospheric Administration (NOAA) - Dr. Nancy Foster Scholarship Program [fellowship, in slate since 2026-11-10] — NOAA Oceanography Scholarship

### Function result: load_functions

Loaded: corpus_item. They are available from your next step.

### Function result: corpus_item

#4 [paper] Marine heatwave forecast triggers rapid response strategy for critically endangered red handfish
Authors: Jemina Stuart‐Smith, Tyson J. Bessell, Alistair James Hobday, Rick D. Stuart‐Smith, Ness Delpero, Victor Shelamoff, SD Ling, Tara Kelly
Venue: Conservation Science and Practice
Year: 2026
Link: https://doi.org/10.1111/csp2.70439
Still open/current: yes
Problem (Mycelium's reading): Preventing extinction of the Critically Endangered red handfish (Thymichthys politus) during acute marine heatwaves (MHW) driven by climate change.
Method (Mycelium's reading): A proactive, pre-emptive rescue strategy triggered by climate forecasts and expert workshop assessment, involving the temporary capture of wild individuals, holding them in captivity for three months, and releasing them after the heatwave subsided.
Setting (Mycelium's reading): Wild population of red handfish in Australia during the 2023/2024 El Niño event, specifically January 2024, with in situ water temperatures exceeding records.
Abstract:
Abstract As climate change drives increasingly frequent and severe climatic extremes, effective strategies to prevent extinction of threatened species are urgently needed. Interventions enabling species to survive acute stress may buy time to address other threats and identify long‐term refugia. For the Critically Endangered red handfish ( Thymichthys politus ), forecasts ahead of the 2023/2024 El Niño indicated a high risk of marine heatwaves (MHW). An expert workshop identified these forecasted extremes (>20 or +~3°C) as a severe threat, triggering an emergency rescue to temporarily remove individuals from the wild. Following commonwealth, state and institutional approvals, 25 fish were captured in January 2024 and held in captivity for 3 months. During this period, in situ water temperatures exceeded records, including 80 days more than 2°C above the long‐term mean summer temperature (~17.5°C). Three fish died in captivity and four adults were retained in a captive breeding program, while the remaining 18 individuals were returned after the MHW subsided, with post‐release survival confirmed after 2 months. This represents Australia's first pre‐emptive rescue of a protected marine species and highlights the importance of proactive, adaptive conservation to strengthen capacity in safeguarding threatened species during environmental extremes and long term climate change impacts.

### Function result: corpus_item

#5 [paper] Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
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
