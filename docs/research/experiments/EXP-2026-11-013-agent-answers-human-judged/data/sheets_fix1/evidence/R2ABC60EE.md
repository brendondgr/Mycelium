# R2ABC60EE

## Question

Could this paper help the Plastic pathways project? Say why or why not.

## Answer

Yes, this paper could be very helpful for the Plastic pathways project (#3).

The project is currently focusing on tracing floating debris to beaches and is in the process of checking its beaching model against field surveys. Paper #1 provides a "tide-resolving beaching kernel" specifically for marine litter tracking, including the code and aggregated results from field records in Korea. Since the project uses Lagrangian particle tracking and is specifically looking at beaching, the three-phase beaching kernel and the associated scripts for particle-tracking experiments in this paper could provide a useful method or benchmark for your current model checks.

## Evidence

### Reference numbers in this conversation

- #1: [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
- #2: Marine heatwave early warning
- #3: Plastic pathways

### Function result: load_functions

Loaded: corpus_item, corpus_search, projects_get, projects_list, projects_feed. They are available from your next step.

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

### Function result: projects_list

Projects:
- #2 Marine heatwave early warning — lab project, 3 members
- #3 Plastic pathways — lab project, 3 members

### Function result: projects_get

#3
Project: Plastic pathways (scope: lab)
Focus statement: Tracing floating debris from river mouths to beaches with forecast currents and satellite detections, to target clean-ups.
Status: Satellite debris detections run weekly; the beaching model is being checked against last summer's beach surveys.
Progress: 35%
Research areas: marine litter tracking; satellite ocean remote sensing
Keywords: Lagrangian particle tracking; beaching; floating debris detection
State: never confirmed by its members.
Members: Jonah Whitcombe, Priya Raman, Mara Ellison

### Reference cards in view

#1 item: [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
   paper · Zenodo (CERN European Organization for Nuclear Research) · 2026
   read more: corpus_item(item='#1')
