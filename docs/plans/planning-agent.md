# Briefing: Planning Agent — Edge Cases, Failure Modes, and Mitigations

**Component:** Planning agent only.
**Scope:** Discovery / liveness, intent reasoning, the self-evaluating ReAct loop, loop control, and the emitted plan. Everything downstream of the plan — specialist query generation, connector enforcement, synthesis, orchestration — is out of scope and is **not** covered here.
**Purpose:** A single reference for validating that the planner produces correct, grounded, bounded plans. Each failure is paired with a concrete mitigation that lives inside the planner or its immediate inputs.

> Implementation: `web/backend/apps/planner/`. The briefing's ATT&CK/CAPEC examples
> are illustrative; the Mycelium implementation seeds the example graph sources
> with the lab's own domain (`lab_graph`, `evidence_graph`, `opportunity_graph`)
> sharing canonical join keys (`paper-doi`, `topic-id`). The architecture is
> identical to this briefing.

---

## 0. How to read this document

The planner does one job: **read the source cards, learn which graphs are live, classify the request, and emit a machine-readable plan** (target sources, sub-questions, join keys, traversal limits, unsupported parts). It routes; it never queries. So its failures are all about *what it decides to ask for*, and the defense is a self-evaluation gate that checks the draft plan against ground truth before it leaves the agent.

Each entry follows the same shape:

- **What goes wrong** — the observable symptom.
- **Why** — the root cause.
- **Mitigation** — what the planner does about it.

Severity tags: **[blocker]** the plan is wrong or unsafe; **[degrade]** the plan is honestly partial; **[noise]** wasted cost/latency without a wrong plan.

Governing principle for this component: **the LLM drafts, deterministic code grades.** The plan is only as trustworthy as the self-eval gate standing behind the model's judgment.

---

## 1. Inputs to the planner

The planner's only ground truth is the set of source cards and the live-source view. If those are wrong, the plan inherits the error before reasoning even starts.

### 1.1 Card the planner reads is internally inconsistent **[blocker]**
- **What goes wrong:** The planner routes to a label or relationship that the card describes in prose but the graph doesn't actually have.
- **Why:** Card drift — hand-authored descriptions diverge from introspected structure.
- **Mitigation:** The planner reasons only over the **introspected fields** (`node_labels`, `relationship_types`, `allowed_edge_patterns`), treating `entity_descriptions` as human context, not routing truth. A consistent card is a precondition the planner assumes and the self-eval gate re-checks (§4.1).

### 1.2 Join key the planner relies on is absent or ambiguous **[blocker]**
- **What goes wrong:** The planner declares a cross-source join that can't actually bind, because the bridge identifier isn't present in both cards or differs in form.
- **Why:** The declared bridge (`technique-id` ↔ CAPEC `MAPS_TO` → `TaxonomyEntry`) lives in two catalogs in two formats.
- **Mitigation:** The planner only proposes a join on a **declared, canonical join key** present in both cards; if the key isn't declared, it does not invent one — it marks the cross-source part unsupported (§3.3).

### 1.3 Live-source view is missing or stale **[degrade]**
- **What goes wrong:** The planner routes to a source that isn't actually running.
- **Why:** The registry lists a source that's down; liveness wasn't checked or was checked too long ago.
- **Mitigation:** The planner consumes a **freshly probed** live-source view (re-probed per request, cached briefly) and treats any source not in it as unsupported. Details in §2.

---

## 2. Discovery / liveness

This is where the planner's "know what graphs are running right now" requirement lives. It must reflect reality at planning time, not registry intent.

### 2.1 Source in the registry but down at planning time **[degrade]**
- **What goes wrong:** The planner builds a plan around a dead backend.
- **Why:** Backends start and stop independently of the card registry.
- **Mitigation:** **Re-probe per request** (cached a few seconds). The planner plans around the live sources and explicitly marks the part that needed the dead source as unsupported — it does not fail the whole request.

### 2.2 Backend up but wrong/empty graph loaded **[blocker]**
- **What goes wrong:** A bare socket/websocket connect succeeds, so the source looks healthy, but the expected data isn't there — the planner routes confidently to an empty graph.
- **Why:** Liveness was checked at the transport level, not the content level.
- **Mitigation:** The probe is a **content probe** — confirm a couple of expected labels exist and node count is non-trivial — not just a connection open.

### 2.3 Probe hangs and stalls planning **[degrade]**
- **What goes wrong:** A slow or half-dead backend makes the liveness probe hang, blocking the whole plan.
- **Why:** The probe has no timeout or shares one with real queries.
- **Mitigation:** The probe gets its **own short timeout**; a non-responding source is treated as down, not waited on.

### 2.4 Probe-once vs probe-per-run mismatch **[degrade]**
- **What goes wrong:** Liveness is checked once at startup; a source that later drops is still planned against.
- **Why:** A single startup probe can't see mid-session changes.
- **Mitigation:** Default to **re-probe per request** with a short cache, so the live-source view tracks the current state rather than the startup state. (Re-checking at execute time belongs to the specialist phase and is out of scope here.)

---

## 3. Planner reasoning (intent → draft plan)

These are the judgment failures in turning a request into sources and sub-questions.

### 3.1 Misrouting — right question, wrong source **[blocker]**
- **What goes wrong:** A CAPEC question is routed to ATT&CK, or vice versa.
- **Why:** Source-selection error under ambiguous phrasing.
- **Mitigation:** Card-grounded routing — each card states what its source covers — and the planner must **record its source-selection rationale** in the plan trace so the choice is inspectable and scorable.

### 3.2 Over- or under-decomposition **[noise / degrade]**
- **What goes wrong:** The planner emits unnecessary sub-questions / source calls (over), or collapses distinct needs into one and misses part of the answer (under).
- **Why:** Decomposition is a judgment call with no single right answer.
- **Mitigation:** The planner is prompted to avoid redundant calls and to cover every distinct part of the request; both are measured directly on the plan (§6) rather than inferred from downstream results.

### 3.3 Out-of-scope or unsupported request **[degrade]**
- **What goes wrong:** The request needs data neither live source holds, and the planner invents a path to look helpful.
- **Why:** Pressure to answer.
- **Mitigation:** The planner **marks unsupported parts explicitly** — naming what it can't answer and why — and never fabricates a source, label, or mapping.

### 3.4 Ambiguous request resolved silently **[degrade]**
- **What goes wrong:** A vague request is committed to one interpretation with no signal that a choice was made.
- **Why:** The planner picks the most likely reading and moves on.
- **Mitigation:** The planner either flags the ambiguity or **states the assumption it made** in the plan, so a reviewer can see and correct the interpretation.

### 3.5 Traversal limits omitted from the plan **[blocker]**
- **What goes wrong:** A sub-question is emitted without the bounds (`max_traversal_depth`, `max_result_rows`) the downstream phase needs to stay safe.
- **Why:** The planner treated limits as someone else's concern.
- **Mitigation:** The plan schema **requires** per-sub-question limits drawn from the card's safety block; a plan missing them fails the self-eval gate (§4).

---

## 4. Self-evaluation gate

The deterministic check between a drafted plan and an emitted plan. This is the planner's core safety mechanism — the LLM proposes, this gate disposes.

### 4.1 Plan names a dead source or nonexistent label **[blocker]**
- **What goes wrong:** The draft targets a source that isn't live, or a sub-question references a label/edge not in that source's card.
- **Why:** The model reasoned past the ground truth.
- **Mitigation:** Before emit, the gate validates **deterministically**: every named source is in the live-source view; every sub-question's entities exist in that source's card; declared join keys are real and canonical; per-sub-question limits are present and within the card's safety bounds. Any failure routes the plan back to revise — the model never grades its own homework.

### 4.2 Gate is too weak (rubber-stamps bad plans) **[blocker]**
- **What goes wrong:** The gate passes a plan that later proves unroutable, defeating the loop's purpose.
- **Why:** The check relied on the LLM's self-assessment instead of code.
- **Mitigation:** Keep the gate **fully deterministic** — set membership against card fields and the live-source view, not a model "does this look right?" prompt. This is what keeps the loop honest.

### 4.3 Gate is too strict (rejects valid plans) **[noise → degrade]**
- **What goes wrong:** Correct plans get bounced, the loop churns, and good requests degrade to partial.
- **Why:** Over-tight checks — e.g. demanding an exact phrasing rather than valid structure.
- **Mitigation:** The gate checks **structural validity** (sources live, entities exist, keys real, limits present), not stylistic preferences; ambiguous-but-valid plans pass.

---

## 5. Loop control

The ReAct loop must terminate cleanly whether or not it converges.

### 5.1 Self-eval loop never converges **[noise → degrade]**
- **What goes wrong:** The planner keeps drafting plans that fail the gate and loops indefinitely, burning cost.
- **Why:** Part of the request may be unanswerable, or the model is stuck on a bad framing.
- **Mitigation:** A **max-iterations cap** (2–3 revises). On exhaustion the planner degrades to "here is the partial plan plus the parts I could not resolve" — never an infinite loop, never a fabricated plan to escape the gate.

### 5.2 Revise step ignores the gate's feedback **[noise]**
- **What goes wrong:** The planner redrafts without addressing why the last draft failed, so it fails the same way again.
- **Why:** The failure reason wasn't fed back into the next Thought.
- **Mitigation:** The gate's specific rejection reason is passed into the next iteration, so each revise is informed rather than a blind re-roll.

### 5.3 Loop exits "valid" on a degenerate plan **[degrade]**
- **What goes wrong:** An empty or trivial plan passes the gate (it references nothing invalid because it references almost nothing) and is emitted as success.
- **Why:** "Contains no invalid elements" isn't the same as "answers the request."
- **Mitigation:** The gate also asserts **non-degeneracy** — the plan must address at least the answerable portion of the request, or be explicitly marked partial; a plan that silently drops the request fails.

---

## 6. Validating the planner (how we measure it)

Failures here corrupt the *measurement* of the planner, not the planner itself. The planner is scored on its **plan output**, decoupled from whether downstream phases later succeed.

### 6.1 Scoring the answer instead of the plan **[blocker for evaluation]**
- **What goes wrong:** Planner quality is judged by final end-to-end correctness, so a good plan is blamed for a downstream failure (or a bad plan is excused by a lucky result).
- **Why:** Conflating the planner with the phases after it.
- **Mitigation:** Score the **plan directly** against expected plans: source-selection accuracy, sub-question quality, unnecessary-source-call count, and schema adherence (does it conform to the plan schema, with limits and valid entities). This isolates the planner.

### 6.2 No fixed expected-plan set **[degrade]**
- **What goes wrong:** Without reference plans there's nothing to score against, so judgments are subjective.
- **Why:** Expected plans weren't authored.
- **Mitigation:** Build a small, manually reviewed set of (request → expected plan) pairs, including out-of-scope and partially-answerable requests so the "mark unsupported" behavior is tested, not just the happy path.

### 6.3 Overfitting the planner to its eval set **[degrade]**
- **What goes wrong:** The planner looks strong on the requests it was tuned on and misroutes novel ones.
- **Why:** Tuning and testing on the same requests.
- **Mitigation:** Hold out a portion of the expected-plan set never used during development; freeze passing cases as regression checks.

---

## 7. Quick-reference matrix

| # | Failure | Where | Severity | First-line mitigation |
|---|---------|-------|----------|----------------------|
| 1.1 | Inconsistent card read | Inputs | blocker | Reason over introspected fields; gate re-checks |
| 1.2 | Join key absent/ambiguous | Inputs | blocker | Only join on declared canonical key; else unsupported |
| 2.1 | Source down at plan time | Discovery | degrade | Re-probe per request; mark unsupported |
| 2.2 | Up but empty graph | Discovery | blocker | Content probe, not socket probe |
| 2.3 | Probe hangs | Discovery | degrade | Probe-specific short timeout |
| 3.1 | Misrouting | Reasoning | blocker | Card-grounded routing + recorded rationale |
| 3.3 | Out-of-scope request | Reasoning | degrade | Mark unsupported; never fabricate |
| 3.5 | Limits omitted | Reasoning | blocker | Plan schema requires per-sub-question limits |
| 4.1 | Names dead/fake target | Self-eval gate | blocker | Deterministic validation before emit |
| 4.2 | Gate too weak | Self-eval gate | blocker | Keep gate fully deterministic |
| 5.1 | Loop never converges | Loop control | degrade | Max-iterations cap → partial plan |
| 5.3 | Degenerate plan passes | Loop control | degrade | Non-degeneracy assertion in gate |
| 6.1 | Scoring answer not plan | Evaluation | blocker | Score plan directly vs expected plans |

---

## 8. The single load-bearing principle

For the planner specifically: **the model drafts the plan, but a deterministic self-evaluation gate — checking the draft against the live-source view and the source cards — decides whether it ships.** Every mitigation above is either feeding that gate good ground truth (discovery, card consistency, declared join keys) or making the gate strict enough to catch bad plans and bounded enough to terminate. The planner is validated when that gate provably accepts good plans, rejects unroutable ones, and degrades to an honest partial plan when it can't converge.

---

## 9. Implementation traceability

Implemented in `web/backend/apps/planner/`. Each failure mode maps to the module that mitigates it and the test that proves it.

| # | Mitigation | Module | Test |
|---|------------|--------|------|
| 1.1 | Reason over introspected fields; gate re-checks consistency | `cards.py` (`validate_card_consistency`), `gate.py` | `test_cards`, `test_gate::test_gate_rechecks_card_consistency_before_trusting_it` |
| 1.2 | Join only on a declared canonical key present in both cards | `cards.py` (`supports_cross_source_join`), `gate.py` | `test_cards::test_cross_source_join_keys`, `test_gate::test_gate_rejects_cross_source_join_not_present_in_both` |
| 1.3 / 2.1 | Fresh live-source view; dead source marked unsupported | `discovery.py`, `drafting.py` | `test_discovery::test_down_source_is_excluded_not_fatal`, `test_drafting::test_down_source_part_is_marked_unsupported_not_fabricated` |
| 2.2 | Content probe, not socket probe | `discovery.py` (`probe_source`) | `test_discovery::test_up_but_empty_graph_is_not_live_by_node_count`, `..._missing_expected_labels...` |
| 2.3 | Probe-specific short timeout, enforced with a thread guard | `discovery.py` (`_inspect_with_timeout`) | `test_discovery::test_hanging_probe_times_out_and_is_treated_as_down` |
| 2.4 | Re-probe per request, cached briefly | `discovery.py` (`SourceProber`), `planner.py` | `test_discovery::test_live_view_is_cached_then_reprobed_after_ttl`, `test_planner::test_agent_reprobes_liveness_each_request` |
| 3.1 | Card-grounded routing + recorded rationale | `drafting.py` | `test_drafting::test_routes_evidence_question_to_evidence_graph_only` |
| 3.3 | Mark unsupported; never fabricate | `drafting.py` | `test_drafting::test_out_of_scope_request_is_marked_unsupported` |
| 3.4 | State the assumption made | `drafting.py` (`_assumptions`) | `test_drafting` (assumption assertions) |
| 3.5 | Plan schema requires per-sub-question limits within card bounds | `schema.py`, `gate.py` | `test_schema`, `test_gate::test_gate_rejects_limits_over_card_bounds` |
| 4.1 / 4.2 | Deterministic validation before emit | `gate.py` (`evaluate_plan`) | `test_gate` (full module) |
| 4.3 | Structural validity, not phrasing | `gate.py`, `schema.py` | `test_gate::test_gate_accepts_honest_partial_plan` |
| 5.1 | Max-iterations cap → honest partial plan | `loop.py` (`run_react_loop`, `degrade_plan`) | `test_loop::test_loop_degrades_to_partial_after_iteration_cap` |
| 5.2 | Feed the gate's rejection reason into the next revise | `loop.py`, `drafting.py` | `test_loop::test_loop_revises_using_gate_feedback` |
| 5.3 | Non-degeneracy assertion in the gate | `gate.py` | `test_gate::test_gate_rejects_degenerate_plan` |
| 6.1 | Score the plan directly vs expected plans | `evaluation.py` | `test_evaluation` (scorer tests) |
| 6.2 | Fixed expected-plan set incl. out-of-scope and partial | `eval_dataset.py` | `test_evaluation::test_dataset_exercises_unsupported_and_out_of_scope_paths` |
| 6.3 | Held-out regression split | `eval_dataset.py` (`HOLDOUT_CASES`) | `test_evaluation::test_holdout_set_passes_as_regression_check` |

The drafter (`HeuristicDrafter`) is a deterministic, offline stand-in for the "LLM drafts" role; `PlanDrafter` is the protocol an LLM-backed drafter implements. The load-bearing safety property — *deterministic code grades* — holds regardless of which drafter is used.
