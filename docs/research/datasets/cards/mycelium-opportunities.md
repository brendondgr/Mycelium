# Dataset card — Mycelium opportunity corpus

## Identity

| Field | Value |
|---|---|
| Name | Mycelium opportunity corpus — grants, fellowships, conference CFPs |
| Sources | Grants: Grants.gov, NIH Guide, NSF, the EU Funding & Tenders portal, SAM.gov, SBIR (`tools/retrieval/collect/grants/adapters/`). Conferences: OpenReview, ccf-deadlines, OpenResearch, the AMS math calendar, MICCAI, society pages (`…/conferences/adapters/`). Fellowships: Illinois Fellowship Finder |
| Licence | Mixed: public-sector listings (largely public domain or open terms); each conference source's own terms; the Fellowship Finder's site terms |
| Redistributable | Grants and most conference records: largely yes, per source terms. Fellowship text: **No** |
| Version | Rolling |

Until 2026-11 the grants and conference CFPs came from a commercial,
login-only database; the corpus was rebuilt from the public sources above
(open question W10). Records from the earlier source are no longer collected.

## Composition

Grants and fellowships with eligibility prose, deadlines, and sponsor metadata;
~2,989 conference CFP records. Deadlines are normalized into `ContentDeadline`
rows; fellowship eligibility is evaluated by a deterministic rule engine, not an
LLM.

## What still limits publication

The grants and conferences are now collected from public sources, so a
grant or conference result can be reproduced by re-running the collector. The
fellowships are not: the Illinois Fellowship Finder is one university's website,
accessed by a Playwright scrape, and its text cannot be redistributed. So:

- a paper resting on fellowship records cannot ship those records; it can ship
  record ids and labels, and the collector that rebuilds them;
- experiment data under `docs/research/experiments/` that quotes fellowship
  text (eligibility excerpts) should be reduced to ids and labels before it is
  redistributed outside this repository.

Award-linkage ground truth (W7) can be built from the same open sources: profile
each PI from publications strictly *before* the award date, positives = programs
won, negatives = contemporaneous unwon calls. ⚠️ Two hazards, both fatal if
unhandled: temporal leakage (publication-to-grant year gap is the single most
predictive feature in prior work), and *won ≠ applied*, so the positives carry
selection bias.

## Experiments that use it

`EXP-2026-11-001` (department-level precision) and `EXP-2026-11-002`
(announcement baseline) label opportunity records from this corpus. Claim C-005
(eligibility gating) still has no evidence.
