# RF60D60AC

## Question

Who in my lab fits this call, and what expertise would we be missing?

## Answer

Here's what I can see for the **Marine Geology and Geophysics** call (#1) against your lab (#2).

## The call, briefly
NSF's core program for the geology and geophysics of ocean basins and margins — lithosphere structure and tectonics, paleoceanography and sea-level change, submarine volcanology and crustal geochemistry, marine hydrogeology and gas hydrates, sedimentology and diagenesis, mid-ocean ridge and subduction processes, marine geohazards, and coastal processes (geological aspects of hurricanes, sea-level change, erosion, offshore deposition). It funds field data, synthesis of existing data, lab experiments, methods development, and modeling. It's still open, though I don't see a deadline listed in what I have.

## Who in the lab fits
The honest answer: **no one in the lab declares a core geology or geophysics topic.** The closest threads are:

- **Jonah Whitcombe (#4)** — declared interests in marine litter and Lagrangian analysis. The nightly ranking put him among the closest profile matches, and his Lagrangian work is the one thing that touches the call's sediment-transport and offshore-deposition themes. But that's a stretch, not a core fit.
- **Tomás Ferreira-Lind (#7)** — circulation and turbulence, physics-informed ML. Also near the top of the ranking, but his profile is physical oceanography, not geoscience.
- **You (#3)** — data assimilation with ML and ocean extremes. The ranking is close, but again, that's not what this call is asking for.

The ranking percentages are profile-similarity, not a judgment of eligibility — and for lab-mates I can only see declared interests, not their papers.

## What you'd be missing
This is the bigger problem. The call's core slots — **lithosphere structure and tectonics, paleoceanography, submarine volcanology and crustal geochemistry, marine hydrogeology, sedimentology and diagenesis, ridge/subduction processes, and marine geohazards** — are not covered by anyone's declared profile in the lab. Your lab is built around data assimilation, ML, ocean extremes, satellite oceanography, and debris pathways. That's a real mismatch with a geoscience core program.

The one genuine overlap is **coastal processes** (geological aspects of hurricanes, sea-level change, erosion, offshore deposition) — which sits near your ocean-extremes and coastal-manager work. If you were to apply, that would be the most defensible angle, but it would need a geoscience lead or collaborator to carry the core geology/geophysics content.

## What I couldn't check
- I can't see anyone's papers, so I can't confirm demonstrated expertise beyond declared interests.
- I don't see a deadline or eligibility rules (career stage, citizenship, institution type) in what I have for this call.
- Collaborator search is turned off on this instance, so I can't suggest who outside the lab might fill the geoscience gap.

If you want, I can pull the full text of the call to check eligibility and deadline, or look at your projects to see which one could anchor a coastal-processes proposal.

## Evidence

### Reference numbers in this conversation

- #1: [grant] Marine Geology and Geophysics
- #2: Coastal Ocean Intelligence Lab
- #3: Mara Ellison (@demo.mara)
- #4: Jonah Whitcombe (@demo.jonah)
- #5: Priya Raman (@demo.priya)
- #6: Sun-hee Park (@demo.sunhee)
- #7: Tomás Ferreira-Lind (@demo.tomas)

### Function result: corpus_item

#1 [grant] Marine Geology and Geophysics
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

### Function result: read_skill

# Who should apply

1. Read the call (`corpus_item`). Then `knowledge_people_for_call`, which
   returns, per person, the requirement slots they cover and the evidence tier
   of each: **declared** (they said so in their profile), **demonstrated**
   (their own papers), **confirmed in conversation** (they told Mylo and said
   yes when asked).
2. Present people by the slots they cover, strongest evidence first. Say the
   tier in plain words for each claim ("from her papers", "she told Mylo in
   October").
3. Name gaps: slots no one covers. Outside-the-lab suggestions only appear when
   collaborator search is on and people consented; never speculate beyond them.
4. Do not rank people with numbers, and do not judge anyone's eligibility you
   cannot see.

### Function result: read_skill

# Judging a call's fit

1. Read the call with `corpus_item` (deadlines, eligibility, amount, whether it is
   still open). If it is closed, say so first.
2. Read who it is for: `projects_get` for a project, `org_lab` for a lab,
   `me_profile` / `me_interests` for the person.
3. Compare concretely: the call's aims against the project's problem and
   method; its eligibility rules (career stage, citizenship, institution type)
   against what you know; its deadline against the project's milestones.
4. Say what fits, what does not, and what you could not check (eligibility you
   cannot see, a budget you do not know). Never guess eligibility.
5. If the question is who should apply, read the `who-should-apply` skill.

Honesty rules, as in Mylo's reports: no scores or percentages, no hype, no
"perfect fit". One plain sentence on the strongest reason and one on the
biggest doubt. Cite the call and the project by #n.

### Function result: load_functions

Loaded: knowledge_people_for_call, org_lab_members. They are available from your next step.

### Function result: knowledge_people_for_call

Who in #2 Coastal Ocean Intelligence Lab could go after #1 Marine Geology and Geophysics:
- #4 @demo.jonah covers “geology and geophysics of the present ocean basins and margins” [declared: Lagrangian ocean analysis]
Profile fit (from the nightly ranking):
- #7 @demo.tomas — Closest match to Tomás Ferreira-Lind's research profile (68% profile match).
- #4 @demo.jonah — Closest match to Jonah Whitcombe's research profile (68% profile match).
- #3 @demo.mara — Closest match to Mara Ellison's research profile (64% profile match).
Evidence tiers: declared = their profile says so; demonstrated = their papers show it; confirmed in conversation = they told Mylo and said yes. Lab-mates are named on their declared profile only.

### Function result: org_lab_members

Members of #2 Coastal Ocean Intelligence Lab (5):
- #3 Mara Ellison (@demo.mara) — owner, PI; declared interests: Data assimilation with ML, Ocean extremes
- #4 Jonah Whitcombe (@demo.jonah) — member; declared interests: Marine litter, Lagrangian analysis
- #5 Priya Raman (@demo.priya) — member; declared interests: Satellite oceanography, Coastal water quality
- #6 Sun-hee Park (@demo.sunhee) — member; declared interests: Ocean data tools
- #7 Tomás Ferreira-Lind (@demo.tomas) — member; declared interests: Circulation and turbulence, Physics-informed ML

### Reference cards in view

#1 item: [grant] Marine Geology and Geophysics
   grant
   read more: corpus_item(item='#1')
