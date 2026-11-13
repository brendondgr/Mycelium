# RF1F8FDD6

## Question

Summarise where the Plastic pathways project stands, name the three most relevant new papers for it, and suggest one funding opportunity it could apply to.

## Answer

Here's the picture for **Plastic pathways (#2)**:

## Where the project stands

The project has three members — Jonah Whitcombe, Priya Raman, and you. I can't see any confirmed state for it (no recorded problem, method, blockers, or milestones), so I can't tell you how far along it is or what's blocking it. If the team has discussed progress, that hasn't been confirmed in Mycelium yet — you can update the project's state in the app.

## Three most relevant new papers

All three entered the slate this week (2026-11-10):

1. **#4 — "A tide-resolving beaching kernel for marine litter"** (Lim & Hong, 2026, Zenodo). The most directly on-topic: a three-phase beaching kernel plus six other particle kernels for OceanParcels 3.1.4, validated against field records from Uido, Korea, using ROMS flow fields. The deposit includes the code, experiment scripts, and aggregated results — a ready-made reference for particle-tracking methodology.

2. **#3 — "Daily Analyses of the Pacific Regional Ocean Forecast System model"** (Zhang, 2026, Zenodo). A data release of daily analyses from a regional ocean forecast system — useful as a flow-field source for particle tracking, though I can only see the title and no abstract, so I can't say more about its contents.

3. **#7 — "A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery"** (Rong et al., 2026, Remote Sensing). Less directly about plastics, but a strong methodological template: a YOLO11-based detection-and-segmentation framework for low-contrast, curved ocean features in MODIS imagery, applied to a decade of satellite data. The same approach could be adapted to detect or track debris signatures from space.

## One funding opportunity

**#5 — NSF Ocean Technology and Interdisciplinary Coordination (OTIC)** — deadline 2027-02-15, still open. It funds unsolicited proposals for instrumentation and technology development with broad applicability to ocean science. A natural angle for Plastic pathways: developing or adapting particle-tracking and beaching-kernel tooling (à la #4) as a reusable capability for the ocean science community. The other open grants on the slate (#8, #9, #12) are all large-scale Earth-observation/satellite infrastructure calls, which fit less tightly than OTIC.

**Suggested next steps:** confirm the project's current state in the app so Mylo can track it properly, and if the team wants to pursue OTIC, I can walk through the proposal angle in more detail.

## Evidence

### Reference numbers in this conversation

- #1: Marine heatwave early warning
- #2: Plastic pathways
- #3: [paper] Daily Analyses of the Pacific Regional Ocean Forecast System model
- #4: [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
- #5: [grant] Ocean Technology and Interdisciplinary Coordination
- #6: [paper] AgentRMOT: Multi-agent Collaboration for Open-World Referring Multi-object Tracking
- #7: [paper] A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea
- #8: [grant] Preparing demonstration missions for collaborative Earth Observation and Satellite telecommunication for Space solutions (Space Partnership)
- #9: [grant] A stronger Global Ocean Observing System to enhance Europe’s strategic autonomy, climate resilience and biodiversity conservation
- #10: [paper] Building Consensus on Satellite Imagery in Human Rights Investigations across Epistemic Communities: Insights from Journalism and Law
- #11: [paper] Temporal completeness reveals long-term hydroclimatic trend reversal: a multi-temporal remote sensing assessment of Lake Belevi (Türkiye), 2000–2026
- #12: [grant] Digital enablers and building blocks for collaborative Earth Observation and Satellite telecommunications for Space solutions (Space Partnership)

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

Loaded: projects_list, projects_get, projects_feed. They are available from your next step.

### Function result: projects_list

Projects:
- #1 Marine heatwave early warning — lab project, 3 members
- #2 Plastic pathways — lab project, 3 members

### Function result: projects_get

#2
Project: Plastic pathways (scope: lab)
Members: Jonah Whitcombe, Priya Raman, Mara Ellison

### Function result: projects_feed

Current slate of #2 Plastic pathways, in rank order:
- #3 Daily Analyses of the Pacific Regional Ocean Forecast System model [paper, in slate since 2026-11-10] (new) — Daily Analyses of the Pacific Regional Ocean Forecast System model
- #4 Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea" [paper, in slate since 2026-11-10] (new) — Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
- #5 Ocean Technology and Interdisciplinary Coordination [grant, in slate since 2026-11-10] — Ocean Technology and Interdisciplinary Coordination
- #6 AgentRMOT: Multi-agent Collaboration for Open-World Referring Multi-object Tracking [paper, in slate since 2026-11-10] (new) — AgentRMOT: Multi-agent Collaboration for Open-World Referring Multi-object Tracking
- #7 A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea [paper, in slate since 2026-11-10] (new) — A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea
- #8 Preparing demonstration missions for collaborative Earth Observation and Satellite telecommunication for Space solutions (Space Partnership) [grant, in slate since 2026-11-10] — Preparing demonstration missions for collaborative Earth Observation and Satellite telecommunication for Space solutions (Space Partnership)
- #9 A stronger Global Ocean Observing System to enhance Europe’s strategic autonomy, climate resilience and biodiversity conservation [grant, in slate since 2026-11-10] — A stronger Global Ocean Observing System to enhance Europe’s strategic autonomy, climate resilience and biodiversity conservation
- #10 Building Consensus on Satellite Imagery in Human Rights Investigations across Epistemic Communities: Insights from Journalism and Law [paper, in slate since 2026-11-10] (new) — Building Consensus on Satellite Imagery in Human Rights Investigations across Epistemic Communities: Insights from Journalism and Law
- #11 Temporal completeness reveals long-term hydroclimatic trend reversal: a multi-temporal remote sensing assessment of Lake Belevi (Türkiye), 2000–2026 [paper, in slate since 2026-11-10] (new) — Temporal completeness reveals long-term hydroclimatic trend reversal: a multi-temporal remote sensing assessment of Lake Belevi (Türkiye), 2000–2026
- #12 Digital enablers and building blocks for collaborative Earth Observation and Satellite telecommunications for Space solutions (Space Partnership) [grant, in slate since 2026-11-10] — Digital enablers and building blocks for collaborative Earth Observation and Satellite telecommunications for Space solutions (Space Partnership)

### Function result: load_functions

Loaded: corpus_item. They are available from your next step.

### Function result: corpus_item

#4 [paper] Code and aggregated results for "A tide-resolving beaching kernel for marine litter: development and application to field records from Uido, Republic of Korea"
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

### Function result: corpus_item

#3 [paper] Daily Analyses of the Pacific Regional Ocean Forecast System model
Authors: Liwen Zhang
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.24034634
Still open/current: yes

### Function result: corpus_item

#5 [grant] Ocean Technology and Interdisciplinary Coordination
Link: https://www.grants.gov/search-results-detail/45793
Still open/current: yes
Deadline (application): 2027-02-15
Problem (Mycelium's reading): The need for instrumentation development and technology that enhances observational, experimental, or analytical capabilities for the ocean science research community.
Method (Mycelium's reading): The OTIC Program accepts unsolicited proposals for instrumentation development and issues specific announcements for funding opportunities related to Improvements in Facilities, Communications, and Equipment at Biological Field Stations and Marine Laboratories (FSML) and the National Ocean Partners…
Setting (Mycelium's reading): NSF Program Description PD-98-1680
Abstract:
The Oceanographic Technology and Interdisciplinary Coordination (OTIC) Program supports a broad range of research and technology development activities. Unsolicited proposals are accepted for instrumentation development that has broad applicability to ocean science research projects and that enhance observational, experimental or analytical capabilities of the ocean science research community. Specific announcements for funding opportunities are made for additional projects involving Improvements in Facilities, Communications, and Equipment at Biological Field Stations and Marine Laboratories (FSML) and the National Ocean Partnership Program.

NSF Program Desccription PD-98-1680

### Function result: corpus_item

#7 [paper] A Deep Learning Framework for Automatic Detection and Segmentation of Internal Solitary Waves in Satellite Imagery over the Northern South China Sea
Authors: Guocai Rong, Huanhe Dong, Yuan Kong, Ze Liu, Yong Hui Fang
Venue: Remote Sensing
Year: 2026
Link: https://doi.org/10.3390/rs18213843
Still open/current: yes
Problem (Mycelium's reading): Automated extraction of internal solitary waves (ISWs) from satellite imagery is challenging due to their elongated, curved crest lines and low contrast.
Method (Mycelium's reading): YOLO11-ISW, an improved YOLO11-based framework for joint detection and pixel-level segmentation, incorporating Dynamic Snake Convolution (DSConv) for curved structures and the Convolutional Block Attention Module (CBAM) for low-contrast features.
Setting (Mycelium's reading): A MODIS-based ISW dataset from the northern South China Sea; the framework was also applied to MODIS imagery from 2011 to 2020.
Abstract:
Internal solitary waves (ISWs) play an important role in ocean energy transport and mixing, yet their elongated, curved crest lines and low contrast make automated extraction from satellite imagery challenging. To address these challenges, this study proposes YOLO11-ISW, an improved YOLO11-based framework for joint ISW detection and pixel-level segmentation. Dynamic Snake Convolution (DSConv) is introduced to enhance the representation of curved crest-line structures, while the Convolutional Block Attention Module (CBAM) strengthens responses to low-contrast ISW features. A MODIS-based ISW dataset from the northern South China Sea was constructed for model training and evaluation. YOLO11-ISW achieved detection Precision, Recall, and F1-score values of 92.01%, 80.73%, and 86.00%, respectively, and segmentation values of 93.14%, 82.60%, and 87.55%, respectively. The model achieved the highest detection and segmentation F1-scores among the evaluated methods. The segmentation results were further georeferenced to extract ISW crest-line locations, and the framework was applied to MODIS imagery from 2011 to 2020 to investigate satellite-observed ISW spatiotemporal variability. The detected ISWs exhibited pronounced spatial clustering, strong spring–summer seasonality, and clear lunar-cycle modulation, consistent with previous observations in the northern South China Sea. These results demonstrate the potential of YOLO11-ISW for automated, long-term, and large-scale monitoring of ISWs using satellite remote sensing imagery.

### Function result: corpus_item

#9 [grant] A stronger Global Ocean Observing System to enhance Europe’s strategic autonomy, climate resilience and biodiversity conservation
Amount: €50,000,000
Link: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-NATURE-2027-04-01
Still open/current: yes
Deadline (application): 2027-02-16
Problem (Mycelium's reading): The global ocean observing system faces risks to continuity, openness, and resilience due to evolving geopolitical dynamics, reduced engagement by key international partners, and structural gaps in under-observed regions like the deep sea and polar regions, which threatens scientific sovereignty an…
Method (Mycelium's reading): Strengthening the Global Ocean Observing System (GOOS) through the deployment of observation equipment, performing observing system experiments (OSEs) and observing system simulation experiments (OSSEs), applying network optimization approaches, co-creating technology roadmaps with industry, and in…
Setting (Mycelium's reading): Global ocean observing frameworks, specifically the Intergovernmental Oceanographic Commission’s Global Ocean Observing System (GOOS), areas beyond national jurisdiction, and the Copernicus Marine Service.
Abstract:
Expected Outcome:

Proposals are expected to contribute to all the following expected outcomes, in full alignment with the OceanEye initiative:

- scientists, public authorities and businesses benefit from strengthened and resilient global ocean observing capacities, coordinated under the Intergovernmental Oceanographic Commission’s Global Ocean Observing System (GOOS),[1] through the deployment of ocean observation equipment, in particular for the provision of critical observations for marine biodiversity and ecosystem knowledge;

- public authorities prioritise investments on infrastructures and capacity building to advance ocean research, protect and restore ocean health and biodiversity and provide critical services through a global ocean observing system and data delivery that is fit-for purpose, cost efficient and designed across all its components;

- increased EU leadership and strategic autonomy in global ocean observation capabilities, in support of EU climate and biodiversity goals, strengthening the EU’s contribution to and influence within GOOS, and reducing the risk of critical dependencies, notably for key services (i.e. Copernicus Services);

- enhanced collaboration between observation communities, marine research infrastructures, European SMEs and technology providers, maritime industries, and service operators, actionably contributing to the validation, procurement readiness, uptake and large-scale deployment of innovative ocean observing technologies and approaches, in particular for biodiversity observations, while reinforcing the long-term sustainability of the global ocean observing system.

Scope:

The EU has committed to global leadership in climate action, biodiversity protection and ocean governance, notably through the EU Ocean Pact, the EU Ocean Observation Initiative “OceanEye”, the EU Biodiversity Strategy for 2030, the EU Mission Restore our Ocean and Waters, the EU Climate Law, and international commitments such as the Global Biodiversity Framework and Agreement on Marine Biological Diversity of Areas beyond National Jurisdiction (BBNJ). Achieving these objectives requires sustained, global, interoperable and open ocean observations, as well as the knowledge and the capacity to use these observations.

IOC-GOOS, constituting the internationally recognised framework for in situ ocean observations worldwide, provides the global backbone for the development and monitoring of Essential Ocean Variables (EOVs),[2] and underpins European capacities such as Copernicus Marine Service and EU-funded research and innovation activities under Horizon Europe. Sustained and resilient ocean observation is crucial for marine biodiversity conservation and restoration under a changing climate, meaning that maintaining an optimised global ocean observing system is very important to achieve biodiversity goals.

Evolving geopolitical dynamics and reduced engagement by key international partners pose significant risks to the continuity, openness and resilience of global ocean observing systems, in particular in areas beyond national jurisdictions, highlighting the need for reinforced European action to safeguard scientific sovereignty and long-term, reliable observations and predictions. This topic aims to stabilise, further strengthen and operationalise the global ocean observing system and open access to data, with particular attention to the interconnected physical, biogeochemical and biological components relevant to biodiversity conservation and reliable services.

Bringing together the scientific community engaged in the Global Ocean Observing System, proposals should:

- focus primarily on areas beyond national jurisdiction, reinforce and expand the governance frameworks and observing networks of the GOOS operating under IOC-UNESCO[3], and the communities monitoring environmental, biological and ecosystem EOVs, to help address current structural gaps at global scale – (e.g. the polar regions, the deep sea and o
