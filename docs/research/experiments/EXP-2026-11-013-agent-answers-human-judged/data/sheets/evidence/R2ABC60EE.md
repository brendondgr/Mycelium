# R2ABC60EE

## Question

Could this paper help the Plastic pathways project? Say why or why not.

## Answer

Yes — this is a strong fit for Plastic pathways. Here's why:

**What the paper is:**
It's a code and results deposit (Zenodo, 2026) accompanying a manuscript by Lim & Hong on a **tide-resolving beaching kernel for marine litter** tracking. The kernel is built for **OceanParcels 3.1.4** — a particle-tracking framework — and includes a three-phase beaching kernel plus six other particle kernels, along with the scripts and aggregated results used to validate it against **field records from Uido, South Korea**, driven by ROMS flow fields.

**Why it helps Plastic pathways:**

1. **Directly on-topic:** The project is about plastic/debris pathways. This paper tackles the specific problem of how marine litter particles behave near shore — the "beaching" phase — which is a critical endpoint in any debris pathway model.

2. **Practical, reusable code:** It's not just a methods description; the deposit contains the actual kernel code, experiment scripts, and aggregated results. If the project uses or plans to use OceanParcels, this is a ready-made, validated component that could be dropped in or adapted.

3. **Tide resolution matters for coastal pathways:** The kernel explicitly resolves tidal effects on particle transport and stranding. For a project tracking where plastics end up (especially near coasts), this is a non-trivial physical detail that many simpler models miss.

4. **Validated against field data:** The authors compared model trajectories against actual field records from Uido, which gives the project a reference for how well a particle-tracking approach can reproduce real beaching patterns.

**One caveat:** The underlying ROMS flow fields (~37 GB) and full particle trajectories (~32 GB) are only available on request, so if the project needs to run the exact same experiments, there's a data-access step. But the kernel code and scripts are in the deposit itself.

It's already ranked #2 on the project's slate (entered 2026-11-10), which is consistent with this being a good match.

## Evidence

### Reference numbers in this conversation

- #1: [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
- #2: Marine heatwave early warning
- #3: Plastic pathways
- #4: [paper] Daily Analyses of the Pacific Regional Ocean Forecast System model
- #5: [grant] Ocean Technology and Interdisciplinary Coordination
- #6: [conference] 47th IEEE International Geoscience and Remote Sensing Symposium
- #7: [fellowship] Woods Hole Oceanographic Institution (WHOI) - Geophysical Fluid Dynamics (GFD) Summer Graduate Research Fellowship
- #8: [paper] A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea
- #9: [paper] AgentRMOT: Multi-agent Collaboration for Open-World Referring Multi-object Tracking
- #10: [grant] Preparing demonstration missions for collaborative Earth Observation and Satellite telecommunication for Space solutions (Space Partnership)
- #11: [conference] IEEE International Conference on Sensing, Communication, and Networking
- #12: [fellowship] National Oceanic and Atmospheric Administration (NOAA) - Dr. Nancy Foster Scholarship Program

### Function result: corpus_item

#1 [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
Authors: Sehan Lim, Sunwook Hong
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.24075707
Still open/current: yes
Problem (Mycelium's reading): Development and application of a tide-resolving beaching kernel for marine litter tracking.
Method (Mycelium's reading): A three-phase beaching kernel and six other particle kernels for OceanParcels 3.1.4, along with scripts for particle-tracking experiments and result aggregation.
Setting (Mycelium's reading): Field records from Uido, Republic of Korea, using ROMS flow fields and particle trajectories.
Abstract:
Code and aggregated results accompanying the manuscript "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea" (submitted to Marine Pollution Bulletin). The deposit contains:- kernel/kernels.py: the three-phase beaching kernel and six other particle kernels for OceanParcels 3.1.4 (also uploaded separately as kernels.py);- the scripts that ran the particle-tracking experiments and aggregated their output;- the aggregated result files from which every number in the manuscript was taken;- the reproduction record (repro/manifest.json) with its checker. Particle trajectories (about 32 GB) and ROMS flow fields (about 37 GB) are available on request. See README.md for the contents and for verification (sha256sum -c SHA256SUMS).

### Function result: load_functions

Loaded: projects_get. They are available from your next step.

### Function result: load_functions

Loaded: projects_list. They are available from your next step.

### Function result: projects_list

Projects:
- #2 Marine heatwave early warning — lab project, 3 members
- #3 Plastic pathways — lab project, 3 members

### Function result: projects_get

#3
Project: Plastic pathways (scope: lab)
Members: Jonah Whitcombe, Priya Raman, Mara Ellison

### Function result: load_functions

Loaded: projects_feed. They are available from your next step.

### Function result: projects_feed

Current slate of #3 Plastic pathways, in rank order:
- #4 Daily Analyses of the Pacific Regional Ocean Forecast System model [paper, in slate since 2026-11-10] (new) — Daily Analyses of the Pacific Regional Ocean Forecast System model
- #1 Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea" [paper, in slate since 2026-11-10] (new) — Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
- #5 Ocean Technology and Interdisciplinary Coordination [grant, in slate since 2026-11-10] — Ocean Technology and Interdisciplinary Coordination
- #6 47th IEEE International Geoscience and Remote Sensing Symposium [conference, in slate since 2026-11-10] — 47th IEEE International Geoscience and Remote Sensing Symposium
- #7 Woods Hole Oceanographic Institution (WHOI) - Geophysical Fluid Dynamics (GFD) Summer Graduate Research Fellowship [fellowship, in slate since 2026-11-10] — Fluid Dynamics & Debris Transport
- #8 A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea [paper, in slate since 2026-11-10] (new) — A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea
- #9 AgentRMOT: Multi-agent Collaboration for Open-World Referring Multi-object Tracking [paper, in slate since 2026-11-10] (new) — AgentRMOT: Multi-agent Collaboration for Open-World Referring Multi-object Tracking
- #10 Preparing demonstration missions for collaborative Earth Observation and Satellite telecommunication for Space solutions (Space Partnership) [grant, in slate since 2026-11-10] — Preparing demonstration missions for collaborative Earth Observation and Satellite telecommunication for Space solutions (Space Partnership)
- #11 IEEE International Conference on Sensing, Communication, and Networking [conference, in slate since 2026-11-10] — IEEE International Conference on Sensing, Communication, and Networking
- #12 National Oceanic and Atmospheric Administration (NOAA) - Dr. Nancy Foster Scholarship Program [fellowship, in slate since 2026-11-10] — Marine Litter & Coastal Management

### Reference cards in view

#1 item: [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
   paper · Zenodo (CERN European Organization for Nuclear Research) · 2026
   read more: corpus_item(item='#1')
