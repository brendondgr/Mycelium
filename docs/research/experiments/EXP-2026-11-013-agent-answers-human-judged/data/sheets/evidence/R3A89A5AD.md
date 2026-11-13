# R3A89A5AD

## Question

Who runs this funding programme, and is it open now?

## Answer

The Marine Geology and Geophysics Core Program is run by the National Science Foundation (NSF) #1. The program is currently open #1.

## Evidence

### Evidence #1 [grant] Marine Geology and Geophysics
Link: https://www.grants.gov/search-results-detail/295449
Still open/current: yes
Deadline (application): 
Abstract:
The Marine Geology and Geophysics Core Program supports research on all aspects of the geology and geophysics of the present ocean basins and margins, as well as those of the Great Lakes.

The Program supports science that includes:

- Structure, composition, tectonics, and evolution of the oceanic lithosphere

- Paleoceanography, paleoclimate, and sea level change

- Submarine volcanology, petrology and geochemistry of the oceanic crust and upper mantle lithosphere

- Marine hydrogeology, water-rock interaction, seeps and gas hydrates

- Hydrothermal venting and in situ fluid processes, and associated geochemistry

- Geochemical indicators of life operating below the seafloor

- Marine sedimentology, stratigraphy, sediment transport, and diagenesis

- Mid-ocean ridge spreading, back-arc rifting, transform processes, and ocean island/seamount formation and evolution

- Submarine components of subduction zone systems and passive margins

- Marine geohazards (e.g., earthquakes, faulting, mass wasting, geological aspects of tsunamis)

- Coastal processes (e.g., geological aspects of hurricanes, sea-level change, erosion, offshore deposition)

The Marine Geology and Geophysics Program supports acquisition of new field data and the leveraging of and/or synthesis of existing data. The program supports analytical and laboratory experimental projects, methods development, and modeling. All activities should have relevance to and advance the understanding of marine geoscience processes. The Program interfaces with NSF programs across the Geosciences and across the Agency. For proposals that cross between Programs, proposers should contact the relevant Programs to seek guidance on submission.

NSF Program Desccription PD-17-1620

### Evidence #2 [paper] HOMEROS seismology notebook - 'Project funded by OSCARS - HOMEROS'
Authors: Vasilis Anagnostou, Eleftheria E. Papadimitriou, V. Karakostas
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.22745992
Still open/current: yes
Abstract:
An open, end-to-end Jupyter notebook that builds an earthquake catalogue from continuous seismic waveforms using machine-learning phase picking. Starting from nothing but a station list and a date range, it downloads open FDSN data, picks P and S arrivals with a neural network, associates them into events, estimates local magnitudes, and exports a catalogue, a map, and a phase file ready for double-difference relocation. The demo region is the central Ionian Islands and western mainland Greece, one of the study areas of the HOMEROS project (Harmonising Observations from Multi-hazard Environments in Research for Open Science). Nothing in the workflow is specific to that region: the search area, station list, and date range are all parameters in a single configuration cell. What the notebook does The workflow is organised as a daily batch pipeline, so it scales to long time spans without running out of memory. Each stage corresponds to a section of the notebook. Station metadata. A response-level StationXML inventory is requested from the configured FDSN providers (NOA, with EIDA as fallback). Wildcard channel requests are expanded against the inventory into exact three-component triplets, so only channels that actually exist are requested. The inventory is cached and reused on later runs. Daily waveform download. For each day, one folder is created and filled with one full-day (86 400 s) MiniSEED file per component. Each trace is merged, padded, resampled to a common sampling rate, detrended, and instrument-response-corrected at download time. Downloads run in a thread pool, fall back across providers, skip files already present, and record the outcome of every request in a per-day JSON manifest. Phase picking. PhaseNet is applied through SeisBench using the pre-trained INSTANCE weights. The network outputs continuous P and S probability traces, converted to discrete picks at a configurable threshold. A CUDA device is used automatically when available. Association. Picks are grouped into events with PyOcto, using 4D space–time partitioning over the configured latitude, longitude and depth volume with a homogeneous velocity model. Association runs day by day on a station table filtered to the stations that produced picks that day. Local magnitude. For each event, the horizontal components of each contributing station are simulated to a Wood–Anderson instrument, the peak amplitude is measured in a 3 s window anchored on the S pick, and a station ML is computed with a standard distance correction. The event magnitude is the median of the station values. Figures and export. The notebook maps epicentres and stations, plots associated picks per station, and writes a hypoDD-format phase file ready for double-difference relocation. Demo run The notebook is archived with the outputs of a two-day run over 23 requested stations from networks HT, HL, HP and HA, covering 1–2 March 2026: 3 494 PhaseNet picks, 28 associated events, and a local magnitude for every event. Two days is a demonstration size; the same notebook runs unchanged over months of data by changing a single parameter, since the per-day loop releases waveform memory and clears the GPU cache between days. Outputs Per-day and merged pick tables, pick-to-event assignment tables, and an event catalogue in CSV, with one row per event giving origin time (UTC), latitude, longitude, depth, ML, and the number of stations used. Per-day download manifests and a processing summary recording traces, picks and events per day. An epicentre and station map, a picks-per-station figure, and a hypoDD-format phase file. Scope and caveats This is a teaching and demonstration workflow, not a production catalogue pipeline. Hypocentres are association-grade: they come from a homogeneous velocity model and are meant to be good enough to group picks, not to be final, which is why a hypoDD phase file is exported. Magnitudes are approximate, using a non-local distance correction with no station correct

### Evidence #3 [paper] A novel approach for evaluating scientific productivity and visibility of FP7 projects: the complementarity of reported publications and funding acknowledgement
Authors: Niliek Silva Alés, Antonio Perianes‐Rodríguez
Venue: Revista española de Documentación Científica
Year: 2026
Link: https://doi.org/10.3989/redc.2026.3.1905
Still open/current: yes
Abstract:
Research funding is crucial for fostering scientific collaboration, ensuring that the objectives defined in scientific policies are met and determining the influence of research within the scientific community. The Seventh Framework Programme (FP7) was the European Union’s main funding instrument for the 2007-2013 period. This macro programme was structured into specific schemes to strengthen European economic growth, sustainability and global leadership. The main goal of this study is to analyse European funding and its scientific productivity based on funded projects and publications. The metadata on funding required thorough data cleaning, and the three open sources used‒CORDIS, Open Funder Registry (OFR) and Research Organisation Registry (ROR)‒had to be standardised. The FP7 project list was imported into a relational database, and the EurSciVoc taxonomy was used to evaluate the data by discipline areas. More than two out of three projects were funded under three schemes: FP7-PEOPLE, FP7-IDEAS-ERC and FP7-ICT. One third of the projects with funding acknowledgements in OFR had no publications reported in CORDIS. These new unreported publications had a significant influence on their scientific fields, adding another 60% to the tallies of projects, publications and funding. The results confirm the advantages of evaluating funding activities using several open data sources.

### Evidence #4 [paper] The MESOSCAN Dataset: A Collection of Mesofauna Images from UK Forest and Peatland Soils
Authors: T.C. Lukins, Thomas Ashton, Ainoa Pravia
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.15755210
Still open/current: yes
Abstract:
A UK forest and peatland soil mesofauna image dataset collected by Forest Research from 2024 to 2025 onwards. Mesofauna are arthropods that live in the soil ranging from approximately 2mm down to 0.2mm in size. Their biodiversity is a key indicator to the health and sustainability of the soil. This dataset is a systematic attempt at collecting and curating valuable images that can be used to help recognise specimens, and to provide training data to machine learning systems that can substantially automate identification and make monitoring more scalable. An example, baseline, machine learning model is provided to validate the data and to illustrate how it can be used - see the ./notebooks folder for this. Highlights: Currently 2600+ training images across 35 taxa each 1600x1600 pixels. Samples were currated from 21 sites across the UK with specimens taxonmically identified prior to imaging. Emphasis has been on creating a varied and extensive range of views for a number of specimens. A selection of realistic and independent test image are provided from cluttered assemblages. Structure The dataset is principally focused on mites (Acari) and springtails (Collembola) which together make up of the majority of mesofauna biomass of soil samples. It organises the data within a (simplified) taxonomic structure reflected by the following directory levels contained in the ./train folder: Class Group Family Genus Species Acari Mesostigmata Trachytidae Trachytes aegrota Acari Mesostigmata Uropodidae Uropoda minima Acari Mesostigmata Rhodacaridae Rhodacarellus silesiacus Acari Mesostigmata Parasitidae Paragamasus Acari Mesostigmata Veigaiidae Veigaia nemorensis Acari Astigmata (_nymphs) Acari Oribatida Galumnidae Acrogalumna longipluma Acari Oribatida Scheloribatidae Liebstadia similis Acari Oribatida Phthiracaridae Steganacarus michaeli Acari Oribatida Phthiracaridae Phthiracarus silesiacus Acari Oribatida Brachychthoniidae Sellnickochthonius zelawaiensis Acari Oribatida Nanhermanniidae Nanhermannia coronata Acari Oribatida Nanhermanniidae Nanhermannia coronata (_nymphs) Acari Oribatida Malaconothridae Malaconothrus monodactylus Acari Oribatida Euzetidae Euzetes globulus Acari Oribatida Hypochthoniidae Hypochthonius rufulus Acari Oribatida Euphthiracaridae Acrotritia duplicata Acari Oribatida Oppiidae Oppiella nova Acari Oribatida Quadroppiidae Quadroppia Acari Oribatida Camisiidae Platynothrus peltifer Acari Oribatida Camisiidae Platynothrus peltifer (_nymphs) Acari Oribatida Achipteriidae Parachipteria punctata Acari Oribatida Peloppiidae Ceratoppia bipilis Acari Oribatida Ceratozetidae Ceratozetes gracilis Acari Oribatida Nothridae Nothrus pratensis Acari Oribatida Nothridae Nothrus pratensis (_nymphs) Acari Endeostigmata Nanorchestidae Nanorchestes Acari Prostigmata Eupodidae Collembola Entomobryomorpha Isotomidae Folsomia penicula Collembola Entomobryomorpha Isotomidae Isotomiella minor Collembola Entomobryomorpha Isotomidae Parisotoma notabilis Collembola Entomobryomorpha Entomobryidae Lepidocyrtus lignorum Collembola Poduromorpha Neanuridae Friesea truncata Collembola Neelipleona Neelidae Megalothorax minimus Collembola Symphypleona Sminthurididae Sminthurides malmgreni At any level within this folder structure images can be stored - according to the taxonomic level of identification that has been resolved. For example, where exact species have been identified the images taken will be found in the very specific folder for that species, whereas more generic identification will be found further up the hierarchy. When specimens cannot be resolved - or else form morphotypes - then a subfolder (begining with an _ underscore) will be created at that point in the taxonomy (e.g. _nymphs). Contents Alongside this README.md file (with example image mesoscan.png) plus the LICENCE file, this dataset contains: MESOSCAN.csv - Top level Excel/OpenOffice spreadsheet /train - Top level folder containing training images /scripts - Some utility Python

### Evidence #5 [grant] Pilot access schemes to Technology Infrastructures for European startups, scaleups and innovative SMEs (CSA)
Amount: €200,000–€12,500,000
Link: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-CL4-2027-01-MAT-PROD-47
Still open/current: yes
Deadline (application): 2027-02-02
Abstract:
Expected Outcome:

Proposals should demonstrate the following expected outcomes:

- A sound understanding of the specific needs of industrial users (including but not limited to innovative SMEs, startups and scaleups) for Technology infrastructure services in specific priority areas including but not limited to advanced materials, clean energy, or health and biotechnology;

- Increased opportunities for industrial users for development, testing, up-scaling and deployment of new technologies via the use of services offered by Technology Infrastructures;

- Strengthened innovation and technology development capacity of European SMEs, startups and scaleups via improved access to Technology Infrastructures;

- Attractiveness and effectiveness of the developed access schemes for broadening the range of Technology Infrastructures users, especially for startups and scaleups, including with transnational access.

Scope:

Startups, scaleups and other innovative SMEs require access to state-of-the-art research and technology facilities, equipment and expertise to test, upscale, validate new products and technologies, shortening the time-to-market and increasing the chances for a successful commercialisation. Access mechanisms to Technology Infrastructures as well as access contracts and collaboration or service provision agreements are often complex, while the costs of using such infrastructures can significantly surpass the financial capacities of growing innovative companies.

The action will develop and test pilot multi-site access schemes for startups, scaleups and other innovative SMEs, involving a critical mass of Technology Infrastructures operators and users in priority areas (including but not limited to advanced materials, clean energy, or health and biotechnology). It should build on existing initiatives with already developed single access points to a comprehensive set of facilities and services in a selected technology area, like for example Open Innovation Test Beds or other integrated networks, that allow for a quick deployment of a common access scheme.

The action should include setting-up a pilot centrally managed and funded access programme, allowing companies quick access to the needed services, with simplified and standardised access conditions applicable across the EU, to be coordinated and in line with the work on the envisaged European Charter of access for industrial users to research and technology infrastructures. While the focus shall be the provision of access and support services to companies, the action can also include enhancing the accessibility and usability of technology infrastructure services to ensure that they meet the evolving needs of users.

The action should aim at significant broadening of the user base of the technology infrastructures to address the needs of startups and scaleups that do not have access to such facilities in their local ecosystems. To this end, proposals should include the development and implementation of activities to increase the visibility and promote and demonstrate the uptake of technology infrastructures services provided to users across the EU.

Furthermore, proposals should aim to enhance transnational and multisite collaboration among Technology Infrastructures fostering the building of technology infrastructures ecosystems, the sharing of experience, resources, and best practices in management, service offer, staff exchange and networking. Proposals may also benefit, especially for communication and dissemination activities, from sharing best practices and taking stock of what other relevant projects are developing in the field of Technology Infrastructures.

Achieving technological leadership for Europe’s open strategic autonomy in raw materials, chemicals and innovative materials (2026-27)

### Evidence #6 [paper] Dataset and code supplement to the scientific paper "Design and implementation of a location-agnostic and control-oriented load surrogate model for wind turbines"
Authors: Adrien Guilloré, Andreas Vad, Filippo Campagnolo, Carlo L. Bottasso
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.23372270
Still open/current: yes
Abstract:
Dataset and code supplement to the scientific paper "Design and implementation of a location-agnostic and control-oriented load surrogate model for wind turbines" submitted for review on Wind Energy Science journal. Authors: Adrien Guilloré, Andreas Vad, Filippo Campagnolo, Carlo L. Bottasso Wind Energy Institute, Technical University of Munich, Germany 85748 Garching bei München, Germany Contact: adrien.guillore@tum.de Funding: This work has been supported by the MERIDIONAL and the SUDOCO projects, which receive funding from the European Union’s Horizon Europe Programme under the grant agreement No. 101084216 and No. 101122256, respectively. Details on the method, implementation and validation of these load surrogate models can be found at: Guilloré, A., Vad., A., Campagnolo, F., and Bottasso, C. L.: Design and implementation of a location-agnostic and control-oriented load surrogate model for wind turbines, submitted for review on Wind Energy Science journal. Guilloré, A., Campagnolo, F., and Bottasso, C. L.: A control-oriented load surrogate model based on sector-averaged inflow quantities: capturing damage for unwaked, waked, wake-steering and curtailed wind turbines, Journal of Physics: Conference Series, 2767, 032 019, https://doi.org/10.1088/1742-6596/2767/3/032019, 2024. This dataset and load surrogates were generated using the following open-source softwares and data: FAST.Farm with wake-added turbulence (Kretschmer, M., Jonkman, J., Pettas, V., and Cheng, P. W.: FAST.Farm load validation for single wake situations at alpha ventus, Wind Energ. Sci., 6, 1247–1262, https://doi.org/10.5194/wes-6-1247-2021, 2021.) TurbSim (Jonkman, B. J.: TurbSim User’s Guide: Version 1.50, Tech. Rep. NREL/TP-500-46198, National Renewable Energy Laboratory (NREL), 1050 https://doi.org/10.2172/965520, 2009.) Aeroelastic model of the IEA 3.4MW reference wind turbine (Bortolotti P, Canet H, Dykes K et al. IEA Wind TCP Task 37: Systems Engineering in Wind Energy - WP2.1 Reference Wind Turbines. United States: N. p., 2019. Web. doi:10.2172/1529216.) and its version for OpenFAST obtained from (https://github.com/IEAWindSystems/IEA-3.4-130-RWT) FLORIS v4.5, https://doi.org/10.5281/zenodo.17186844, 2025. TensorFlow python code suite, to build artificial neural networks for the surrogates (Abadi, M., Barham, P., Chen, J., Chen, Z., Davis, A., Dean, J., 970 Devin, M., Ghemawat, S., Irving, G., Isard, M., Kudlur, M., Levenberg, J., Monga, R., Moore, S., Murray, D. G., Steiner, B., Tucker, P., Vasudevan, V., Warden, P., Wicke, M., Yu, Y., and Zheng, X.: TensorFlow: Large-Scale Machine Learning on Heterogeneous Systems, https://www.tensorflow.org, software available from tensorflow.org, 2016). This folder contains: "00_All_datasets_IEA_3400/IEA_3400 - Surrogate Training Validation Dataset_ Averaged Seeds.h5": the full post-processed dataset of 30783 points (each averaged over 24 seeds realizations for statistical convergence of the inputs and the outputs) built from FAST.Farm simulations using three IEA 3.4MW reference wind turbines, used for training and validation of the surrogates. "00_All_datasets_IEA_3400/IEA_3400 - Surrogate Training Validation Dataset_ All Seeds.h5": the same as 1. including all non-aggregated turbulent seeds results for any seed-based analysis. "00_All_datasets_IEA_3400/IEA_3400 - Farm Level Testing Dataset_ Averaged Seeds.h5": the full post-processed dataset of 735 points (each averaged over 24 seeds realizations for statistical convergence of the inputs and the outputs) built from FAST.Farm simulations using five IEA 3.4MW reference wind turbines, used for testing the surrogates on a new wind farm. "00_All_datasets_IEA_3400/IEA_3400 - Farm Level Testing Dataset_ All Seeds.h5": the same as 3. including all non-aggregated turbulent seeds results for any seed-based analysis. "01_Main_recommended_surrogates": the trained and directly applicable load surrogate functions for each output channels of interest, as TensorFlow Keras mo

### Evidence #7 [paper] doi:10.70132/j7356948637
Venue: Insights into Regional Development
Year: 2026
Link: https://doi.org/10.70132/j7356948637
Still open/current: yes
Abstract:
Africa's development financing has been shaped by traditional international institutions such as the Bretton Woods Institutions (BWIs) and newer entities, such as the New Development Bank (NDB), established by the BRICS countries.The BWIs, particularly the International Monetary Fund (IMF) and the World Bank, have provided critical financial support.Still, they are often criticised for their rigid conditionalities, which limit African countries' autonomy in development planning.In contrast, the NDB offers a more flexible, partnership-driven approach despite facing governance and institutional capacity challenges.The study explores the feasibility and challenges of collaboration between BWIs and the NDB to fund development projects in Africa.Addressing a gap in the literature, the research investigates how these institutions can work together to create a more balanced and effective development model that prioritises both economic growth and social development.The problem lies in the stark differences between the BWIs' conditionality-driven model and the NDB's evolving governance structures, which present challenges to achieving sustainable development in Africa.Utilising a qualitative research design, the study gathered data through semi-structured interviews with key stakeholders, including policymakers and development experts, and document analysis of institutional reports.Findings indicate that while BWIs' strict conditionalities promote fiscal discipline, they often undermine social development by prioritising short-term economic goals.Conversely, the NDB's flexibility supports greater local ownership but struggles with governance and accountability issues.Both institutions are influenced by the geopolitical interests of their dominant member states, complicating their effectiveness in promoting Africa's long-term development.Recommendations include creating a hybrid financing model that combines the financial discipline of BWIs with the flexibility of the NDB, strengthening governance through joint capacity-building initiatives to address institutional capacity gaps, and ensuring that development projects align with Africa's long-term strategic goals.Future research should focus on longitudinal studies to assess the lasting impacts of these institutions on sustainable development outcomes in Africa.

### Evidence #8 [paper] The nature and evolution of EU funds for migration and asylum: introducing the MigFund dataset 2000–2023
Authors: Federica Zardo
Venue: European Political Science
Year: 2026
Link: https://doi.org/10.1017/s168209832610068x
Still open/current: yes
Abstract:
Abstract This article introduces the MigFund dataset, a comprehensive resource that traces the European Union’s financial commitments to migration and asylum from 2000 to 2023. Developed in response to long-standing calls to ‘follow the money’ in EU migration governance, the dataset records over 1,700 funding measures across internal and external programmes, disaggregated by sub-policy area, target group, geographic scope, and degree of restrictiveness. Drawing on the literature on policy tools, the article conceptualises EU funding as an expression of institutional preferences, bureaucratic negotiation and strategic framing, shaping and shaped by evolving policy priorities. A key contribution of the dataset is its coding of each measure along a restrictive-to-open continuum, enabling researchers to assess how EU financial tools promote either mobility and protection or containment and control. The article details the dataset’s structure and coding logic and presents key descriptive findings on the evolution of EU funding, showing a steady expansion of resources and increasing complexity in the programming landscape. Through this empirical lens, the article invites a reconsideration of financial instruments as autonomous policy tools, capable of reinforcing, offsetting or reconfiguring broader migration policy logics. MigFund thus provides a basis for macro- and meso-level analyses of funds in EU studies, migration studies and public policy more broadly.

### Evidence #9 [grant] Call for proposals for operating grants in 2027 to non-governmental organisations: financial contribution to the functioning of health non-governmental organisations implementing one or more specific
Link: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/EU4H-2027-SANTE-OG
Still open/current: yes
Deadline (application): 2027-01-19
Abstract:
Expected Impact:

Through their core operational activities, health NGOs will deliver health promotion, capacity building and networking, and contribute to the optimisation of healthcare activities and practices by providing feedback from patients and facilitating communication with patients.

The beneficiaries are expected to further demonstrate in their proposals the Union added value of their activities and commit to deliver concrete results such as: online materials, webpages, manuals and tools on case studies promoting health in schools, factsheets and relevant literature, materials for teachers on health literacy, and assistance and promotion of twinning with other schools in the Union capacity-building and training activities to reduce the impact of risk factors for non-communicable diseases; new approaches to promote healthy and sustainable diets; expert guidance and peer-to-peer connections; and collaborate in shared areas of activity.

Objective:

The objective is to ensure the participation of health NGOs in activities that are necessary to implement one or more specific objectives of the EU4Health Programme. Operating grants should provide support to their functioning in 2027 for activities including awareness raising on various health aspects, communication and dissemination, capacity building and training, expert collaboration and networking.

Scope:

Activities proposed must comply with Commission Guidance on the funding for activities related to the development, implementation, monitoring and enforcement of Union legislation and policy.

### Evidence #10 [paper] From financial autonomy to performance-based funding for sustainable development financing of higher education institutions in Uzbekistan
Authors: Ziyodakhon Abdualimova, Rakhmatilla Kholmuradov, Sharifa Hamroyeva, Hilola Yusupova, Nilufar Valiyeva
Venue: Frontiers in Education
Year: 2026
Link: https://doi.org/10.3389/feduc.2026.1920875
Still open/current: yes
Abstract:
The expansion of HEIs in Uzbekistan has generated a new finance problem: universities must expand access, develop research capacity and modernise infrastructure with still-constrained public budgets. This paper presents a policy-oriented model relating financial autonomy to sustainable development funding of HEIs during Uzbekistan's shift from cost-based to rating-linked performance funding. The study presents the Financial Autonomy and Development Capacity Index (FADCI), combining revenue autonomy, expenditure flexibility, research financing, infrastructure capacity and governance readiness, corroborated by expert AHP weighting and piloted on six HEIs. The analysis suggests that performance-based funding from 2027 is likely to promote sustainable development financing only if autonomy is combined with transparent data, equalisation, internal audit capacity and mission-sensitive metrics. The methodology can be replicated by emerging higher education systems moving from budget dependence to accountable financial autonomy.

### Evidence #11 [paper] QNFO Funding Strategy — Verified Funder Landscape & Shortlist
Authors: Rowan Brad Quni-Gudzinas
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.21922588
Still open/current: yes
Abstract:
This paper presents a verified funder landscape and fit-score shortlist for sustaining QNFO, a two-year-old, solo-run, AI-assisted research platform that has produced an open corpus of approximately 1,000 method papers across seven program areas. Every funder fact was verified by live HTTP retrieval on 2026-08-13 across twenty-six pages spanning Web3 and IPFS ecosystem grantors, open-science philanthropy, and decentralized-science programs; anything not verified live is explicitly flagged. The analysis scores eleven funders on eligibility for an unaffiliated individual, topical fit with decentralized and epistemics-oriented research, and application friction, yielding a weighted ranking led by NLnet NGI Zero (calls open September 3, 2026; deadline November 3, 2026, 12:00 CEST) and Emergent Ventures, followed by the Foresight Institute, Filecoin Foundation, the Ethereum Ecosystem Support Program, Gitcoin, and the Effective Altruism funds. A sequencing calendar spans August 2026 through 2027, including the Sovereign Tech Agency Fellowship cycle. The paper documents application-readiness gaps (legal entity, residency, tax position, public identity), per-funder pitch skeletons, and framing cautions, including the risk of presenting corpus volume as rigor. It closes with an agent-executable action plan.

### Evidence #12 [paper] The Fleming Fund: Key Features of Design and Approach to Strengthening Antimicrobial Resistance Surveillance in Low- and Middle-Income Countries.
Authors: Shorten, Tim, Clarke, Jemima, Drake, Archibald, Gupta-Wright, Ankur, von Und Zur Mühlen, Milena, Wesangula, Evelyn
Venue: Clinical infectious diseases : an official publication of the Infectious Diseases Society of America
Year: 2026
Link: https://pubmed.ncbi.nlm.nih.gov/42895839/
Still open/current: yes
Abstract:
This paper examines the Fleming Fund as a major long-term investment in strengthening antimicrobial resistance (AMR) surveillance in low- and middle-income countries. Established by the UK Department of Health and Social Care in 2015, the Fund committed up to £498 million to support surveillance capacity across 25 countries in Africa and Asia through a One Health approach spanning human, animal and environmental health. The paper situates the Fleming Fund within wider global concern about AMR and highlights surveillance as essential for stewardship, policy and international coordination. It describes the Fleming Fund's design logic, governance arrangements, grant architecture and evolving strategic priorities, with particular attention to how the program combined laboratory strengthening, workforce development, data systems, quality assurance, sampling pathways and multisectoral coordination to generate credible and usable AMR data. The analysis also examines the Phase 2 shift from an initial emphasis on data generation toward greater attention to data interpretation, dissemination and use in policy and practice. Drawing on program documentation, evaluation evidence and stakeholder perspectives, the paper presents the Fleming Fund as an important case of large-scale surveillance system strengthening in resource-constrained settings. It argues that the Fund offers wider lessons on the time, coordination and institutional embedding required to move from externally supported capacity building toward sustainable national surveillance functions. These lessons are relevant to future AMR investments and to broader debates on global health security, health systems strengthening and One Health implementation.

### Evidence #13 [paper] Fiscal Foundations: Assessing Financial Management as a Driver for NGO Institutional Development in East Africa
Authors: Kenneth Nyesige, Akashraj Devanga Pruthviraj, Abraham Kuol Nyuon
Venue: East African Journal of Business and Economics
Year: 2026
Link: https://doi.org/10.37284/eajbe.9.3.5729
Still open/current: yes
Abstract:
Purpose: This study evaluated the effect of financial management on the institutional development of non-governmental organisations (NGOs) in Kenya, Uganda, Tanzania, and South Sudan for the period 2015–2021. Methodology: A concurrent mixed-methods design was adopted. The quantitative component employed a cross-sectional survey of 476 respondents from 28 NGOs across four countries (94.4% response rate), analysed using descriptive statistics, Pearson correlation, multiple regression, and ANOVA. The qualitative component comprised 48 in-depth interviews, analysed using thematic analysis. Findings: Financial management components collectively explained 53.9% of the variance in institutional development (R² = 0.539, F = 184.267, p < 0.001). Financial reporting emerged as the strongest predictor (β = 0.287, p < 0.001), followed by strategic budgeting (β = 0.234, p < 0.001), financial controls (β = 0.198, p = 0.001), and donor compliance (β = 0.176, p = 0.006). Organisational age, budget size, and staff size significantly moderated these relationships (p < 0.001). Qualitative findings revealed a persistent tension between donor compliance demands and strategic financial autonomy. Conclusion: Financial management has a significant positive effect on institutional development but is constrained by donor-driven short-termism and limited strategic capacity. Recommendations: NGOs should shift from defensive compliance to strategic financial planning; donors should invest in core funding; and policymakers should establish harmonised reporting standards.

### Evidence #14 [grant] EIC Pre-accelerator - Widening
Amount: €500,000–€1,000,000
Link: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-WIDERA-2027-01-WIDENING-01
Still open/current: yes
Deadline (application): 2027-11-18
Abstract:
Expected Outcome:

This call will increase the innovation potential of deep-tech startups in the Widening countries and enable them to better attract private investments and scale up. It will further strengthen the innovation dimension of the widening component and increase the overall competitiveness of these countries.

The specific outcome expected of this action is increased business, investor, and technology readiness of high potential deep-tech startups in Widening countries to a level where they will:

- be successful in applying and attracting the EIC Accelerator funding and/or;

- manage to secure other private investment and/or;

- attract successfully national or regional funding as alternative funding sources (e.g. through Seal of Excellence programmes).

Scope:

This action focuses on early-stage deep-tech startups which 1) have high-impact innovation technology, product, service, or business model that could create new markets or disrupt existing ones, and 2) have the ambition and commitments to scale up.

The successful applicants need to work on deep tech innovation. Such companies often struggle to attract financing because the technology and investment risks are too high.

In the framework of this call, deep-tech[1] is technology that is based on cutting-edge scientific advances and discoveries and is characterised by the need to stay at the technological forefront by constant interaction with new ideas and results from the lab. Deep-tech innovations are understood to be those that have the potential to deliver transformative solutions, rooted in cutting-edge science, technology, and engineering, including innovation that combines advances in the physical, biological and digital spheres. Deep-tech is distinct from ‘high-tech’ which tends to refer only to R&D intensity[2].

This EIC Pre-accelerator - Widening call is designed to enable promising deep-tech startups to develop further their innovations (from TRL 4 to TRL 5/6)[3], attract the investment amounts needed for scale up in a shorter timeframe and successfully apply and attract funding from EIC Accelerator or other sources.

The applicants are expected to demonstrate in their application that they:

- have completed all elements of TRL 3 (Experimental proof of concept) and therefore the technology is currently at TRL 4 (Technology validated in lab);

- possess the necessary Intellectual Property Rights to ensure freedom to operate and adequate protection of the idea;

- have a clear vision on the intended pathway and route to market. This includes specific milestones together with concrete and verifiable KPIs to assess progress towards the market.

The support will be in awarded by grants max at 70% funding of the eligible costs. 30% co-funding to be covered by the beneficiary through its own resources.

An amount between EUR 500.000 and max EUR 1.000.000 in the form of a lump sum for a period of up to 2 years is considered appropriate.

The requested grant is expected to be used for:

- addressing the investor and market readiness towards commercialisation and deployment (market research, value proposition, business case and business model, prospects for growth, intellectual property protection, competitor analysis etc.) and if relevant, aspects of regulation, certification and standardisation, aimed at getting both the technology and the business idea investment ready and/or;

- the maturation and validation of novel technologies beyond proof of concept to viable demonstrators of the technology in the intended field of application (i.e., from minimum TRL 4 up to TRL 6).

At the end of the EIC Pre-accelerator project, it needs to:

- demonstrate that the technology component of their innovation has at least been validated in a relevant environment (e.g. at least completed all aspects of TRL 5);

- be ready to apply for EIC Accelerator and/or to seek other investors or sources of funding, to enter licensing or collaboration agreements with third parties

### Evidence #15 [paper] Shaping innovation : Studies of public funding for applied research in Sweden, 1970–2021.
Authors: Johanna Fink
Venue: Lund University Publications (Lund University)
Year: 2026
Link: https://lup.lub.lu.se/record/1c8c1203-00f7-46c4-850c-8db9304515fb
Still open/current: yes
Abstract:
Innovation and technological progress have been identified as key drivers of long-term economic growth. However, not all innovation is supporting sustained economic growth or addressing societal concerns such as climate change. Against this backdrop, researchers advocate for active government intervention in shaping technological development, a role that governments have increasingly assumed in recent decades. Yet, it remains unclear where exactly public funds are channeled, and whether this is in line with wider policy objectives.This thesis offers empirical evidence on the allocation of public funding in Sweden between 1970–2021. To this end, a comprehensive database over public innovation funding is created, where individual public funding projects are directly linked to innovation outputs. The database has been used to investigate the quantitative dimension, direction, network additionality, and output additionality of public funding. Sweden is selected as the research subject, since it was among the first countries to actively promote applied research, ranks among the most innovative countries today, and is considered a pioneer in sustainable development.The thesis highlights the importance of public support for innovation development. It shows that public funding is associated with types of innovation projects that are typically less likely to receive private funding, particularly innovations developed by small firms, radical innovation, and green innovation. Innovations involving innovation agencies are more likely to bring together diverse sets of collaborators, which in turn are associated with the development of radical innovations. Finally, public funding shows signs of output additionality, as approved public funding projects are nearly twice as likely to generate significant innovation outputs.

### Evidence #16 [grant] Notice of Intent on Upcoming 2020 TIP Office Funding Opportunity
Link: https://www.grants.gov/search-results-detail/328026
Still open/current: yes
Deadline (application): 2099-01-01
Abstract:
The TIP Office intends to announce its 2020 Funding Opportunity for the annual awards competition process in the upcoming weeks. The TIP Office is finalizing language for the annual awards competition process that includes a number of regional and thematic priorities for funding globally. Recognizing the hard work and effort that is involved in developing applications for funding, the TIP Office is notifying organizations that may be interested in submitting applications that a funding opportunity will be posted in the upcoming weeks. Organizations eligible to apply for this funding opportunity include U.S.-based and foreign non-profits, public international organizations, institutions of higher learning, and for-profit organizations. The 2020 TIP Office Funding Opportunity will be posted on SAMS Domestic, grants.gov, and the TIP Office website. Organizations interested in applying for funding may consider reviewing the information on the TIP Office’s Annual Awards Competition Process in preparation for the funding opportunity. Please note, this is a notice of intent only; an announcement will be made in the upcoming weeks when the 2020 Funding Opportunity is posted. We are not accepting applications at this time.

Link to Opportunity in SAMS Domestic

### Evidence #17 [paper] The Impact of Donor Funding Disruptions Across the Paediatric HIV Care Cascade in Sub-Saharan Africa (2005–2025): A Scoping Review
Authors: Violet Bosire, Jepchirchir Kiplagat, Lilian Muchai, Sara Jewett
Venue: AIDS and Behavior
Year: 2026
Link: https://doi.org/10.1007/s10461-026-05320-1
Still open/current: yes
Abstract:
Paediatric HIV outcomes in sub-Saharan Africa (SSA) have significantly improved over the past two decades, largely due to donor-funded programmes that promote early infant diagnosis (EID), antiretroviral therapy (ART), and community-based service delivery. Despite these achievements, many countries in the region remain highly dependent on external donor financing, raising concerns about the sustainability of paediatric HIV services during periods of funding uncertainty. This scoping review examined how donor funding disruptions impact paediatric HIV service continuity in SSA and their system-level consequences for children. This review included studies published between January 2005 and November 2025. Following the PRISMA-ScR guidelines, studies were analysed using descriptive statistics and narrative synthesis with findings organised across the paediatric HIV care cascade. Across nine studies, donor transitions, especially those related to PEPFAR, were linked to workforce reductions, supply chain disruptions, and the elimination of community-based outreach programmes. These changes contributed to delays in EID, weakened linkage to care, disruptions in ART initiation, and decline in retention. These effects occurred through interconnected health-system pathways rather than isolated programme failures. Overall, the results show that paediatric HIV services remain highly dependent on donor-supported systems, with limited transition preparedness. Transition frameworks should prioritise paediatric service continuity, strengthen health-system resilience, and align financing responsibilities between donors and governments to reduce preventable child morbidity and mortality.

### Evidence #18 [paper] Generating a national snapshot of all publicly reported investments in ecosystem and species conservation across public, private, and philanthropic finance
Authors: Alice Stuart, Sophus zu Ermgassen
Venue: AMBIO
Year: 2026
Link: https://doi.org/10.1007/s13280-026-02464-1
Still open/current: yes
Abstract:
Abstract Scaling up investment in ecosystems is a national and international public policy priority. Evaluations of the total amount spent have been severely criticised, with a lack of transparent reporting, especially of private finance flows, a known limitation. We provide a country-wide snapshot of investment in nature in the UK based on publicly available data, estimating total annual nature finance flows in the UK of ~£1.15bn. Public investment in agri-environment (£389.1m) and grant schemes (£314.8m) accounted for over 60% of identified flows. Private financial flows (£142.4m) consisted of corporate philanthropy (£71.5m), return-seeking investment and loans (£50.7m), and credit and unit purchases (£20.2m). Estimated flows from NGOs and philanthropic grants totalled £388.5m. Interactions between flows mean double counting must be considered when summing. We find major public transparency gaps in nature finance flows, undermining efforts to understand the both the extent of nature finance flows and their effectiveness for nature recovery.

### Evidence #19 [paper] Office of Science Financial Assistance Program (DOE)
Venue: Federal Grants & Contracts
Year: 2026
Link: https://doi.org/10.1002/fgc.35017
Still open/current: yes

### Evidence #20 [paper] Who’s Pulling the Strings? Disclosure of Third-Party Funding Agreements in International Arbitration
Authors: Ilkin Bayramov
Venue: Baku State University Law Review
Year: 2026
Link: https://doi.org/10.30546/224578.012.2026.311
Still open/current: yes
Abstract:
Third-party funding (hereinafter TPF) has emerged as a more significant method for financing international arbitration, permitting underfunded claimants to pursue valid claims and enabling parties to handle procedural risks without exhausting their liquidity.Unlike insurance, loans and contingency or conditional-fee arrangements, TPF has developed from past restrictions on maintenance and champerty into a swiftly growing commercial activity.Certain issues related to TPF have been tackled by institutional regulations mandating the disclosure of third-party funders' existence and identity; nonetheless, the regulatory structure still appears disjointed and insufficient.This article explores the legal and ethical issues associated with TPF, highlighting the conflicts of interest impacting arbitrators, the triangular relationship between lawyers, clients and funders that can lead to control over strategy and influence on the proceedings, as well as the effects of TPF on cost distribution and security for costs.It examines current institutional methods of disclosure and contends that, under specific conditions -especially when funders exert control, maintain extensive termination rights, or limit liability for negative costs -arbitral tribunals need access to significant funding terms.The article ends by supporting measured disclosure authority and broader institutional oversight to protect procedural fairness and the validity of arbitration processes.

### Evidence #21 [paper] Expert insight on the design, implementation, and monitoring of future community benefit funds within the energy transition
Authors: E. Boyle, A. Revez, Aoife Deane, B. Ó. Gallachóir
Venue: Discover Energy
Year: 2026
Link: https://www.semanticscholar.org/paper/0255d82aaededef457ac0966198f350485bcdc76
Still open/current: yes
Abstract:
Increasingly, citizen and public participation are considered central to achieving the energy transition to a low carbon future. Such participation has different dimensions in new energy infrastructure, in terms of both renewable energy installations and additional electricity grid developments. Participation includes active involvement in decision making, the ability to invest in developer-led projects, and capacity for community owned renewable energy projects. This also includes community benefit funding (CBF), whereby a local fund is established by the developer and provided to communities impacted by infrastructural developments. There is a growing body of experience with CBF, but it has not received much attention in the scientific literature. In addition, there is a paucity of analysis of the design, implementation, and evaluation of CBF schemes. This research intervention addresses this gap using a modified Delphi panel approach to explore areas of consensus and divergence on these dimensions of CBF programs. We bring together national and international experts on community benefit funding who work on key areas of relevance such as policy formation, strategy design, fund administration, and community development to deliberate on the role of CBF in supporting future developments towards energy system change. The method implemented draws out lessons learned concerning community benefit funding and insights concerning its future design, implementation, and monitoring from a range of sectors and perspectives. While participant experts within the study are made up of three groups: the public, private and academic sectors, the results have specific application in relation to CBF associated with renewable energy production whereby the financial benefit accrued is long lasting over time. This is critically important in the context of the scale of growth planned and the significant associated levels of CBF that will transfer from private funds to public good. The results highlight where there is consensus and divergence of opinion for the design, delivery, and monitoring of CBF, which can usefully inform policy deliberations as well as advancing knowledge as we see CBF growing in significance both in Ireland and internationally.
