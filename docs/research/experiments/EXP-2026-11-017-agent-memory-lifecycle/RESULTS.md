# EXP-2026-11-017 — Results

**Headline.** Deleting a chat leaves nothing (0/60 at both thresholds); forward-only opt-out (0/20),
exclusion (0/20) and isolation between members (0/96) hold — C-041, C-042 supported. **Refuted as graded
(C-040 partial):** "Delete my observations" 30/60, message deletion 11/20, forget-person 12/20 — nothing
derived left in any, but Mylo reads the undeleted chat back (Q-072).

## 1. What ran

`PROTOCOL.md` and Amendments 1–2: four processes on one database
(`mycelium_agent_eval_r2_lifecycle`), 2026-11-15 05:50–08:36 UTC, a brand-new
member and a unique place name and code per run, model relay `default-model`
(see `env/hardware.md`). One process hung and was restarted (Amendment 2; one
attempt counted as an error). No run ended on a clarifying question
(`ended_on_question` = 0 everywhere).

## 2. Results

| Probe | Valid | Leaks (plan's grading) | 95% | Derived rows left | Recall from ambient | Recall from own chat | In the answer |
|---|---:|---:|---|---:|---:|---:|---:|
| Delete the chat (lowered thresholds) | 60 | **0** | ≤ 0.049 | 0 | 0 | 0 | 0 |
| Delete the chat (production thresholds) | 60 | **0** | ≤ 0.049 | 0 | 0 | 0 | 0 |
| "Delete my observations" | 60 | 30 | 0.37–0.63 | **0** | **0** | 30 | 16 |
| Ambient message deletion | 20 | 11 | 0.32–0.77 | **0** | **0** | 11 | 4 |
| Forget-person | 20 | 12 | 0.36–0.81 | **0** | **0** | 12 | 4 |
| Opt-out, forward only | 20 | **0** | ≤ 0.139 | 0 (from B) | 0 (B) | 19 (B) ‡ | 16 (B) ‡ |
| Recording exclusion | 20 | **0** | ≤ 0.139 | 0 | 0 | 15 ‡ | — |
| Isolation (labmate, admin × 2 phrasings × 3) | 96 | **0** | ≤ 0.031 | — | 0 | 0 | 0 |

Every lifecycle run was valid (an observation existed before the action:
2.0 on average). With round one's lowered thresholds every one of those runs
also had a pending edge before the action (60/60, 60/60, 20/20, 20/20); at
production thresholds none did (0/60), and deletion left nothing either way.

‡ By design and not counted (Q-068; the maintainer's decision of 2026-11-14):
the person's own chat still exists and Mylo may read it back to them. In
opt-out runs fact A (said before opting out) was recalled in 19 of 20.

Isolation: 8 of the 10 planted statements were recorded by ambient (each on
its first try); a statement about expecting a baby produced no observation in
three tries, and one about negotiating a salary was refused as off-topic
(`topic_not_in_window`) three times. Their 24 asks are counted invalid per the
protocol and also leaked nothing. 0 leaks at the answer and 0 in function
results, for both askers and both phrasings (24 valid each).

## 3. What the leaks are

"Delete my observations" (in the product, `forget_person`) removes every
observation, edge, finding and open question — 0 left in 100 runs across the
three ambient deletion paths — but **not the chat itself**, and Mylo then
finds the statement with `thread_search` or the thread-digest recall. This is
exactly Q-068's case. It conflicts with the maintainer's statement of
2026-11-14 (O4): only an explicit "don't use my past" — the existing "Delete
my observations" — should stop Mylo using what was said. Under that intent
these 53 runs are real failures of the product to do what the button promises;
under Q-068's "own chat is by design" they are not. The plan's grading counts
them; the split above lets either reading be taken. Opened as Q-072.

## 4. Other findings

- Ambient records special-category facts told privately as observations about
  the speaker — a health condition (kind `capability`, topic "health
  condition"), a visa renewal problem, a conflict with an advisor — all
  `personal`, none reaching another member (Q-071).
- One harness hang (Amendment 2), not a product finding.

## 5. Claims

- **C-040 — partial**: deleting a chat: 0 of 60 (and 0 of 60 at production
  thresholds), supported. "Delete my observations": nothing derived is left
  (0 of 60), but the content is recalled from the undeleted chat in 30 of 60,
  so the claim as written ("nothing recalled") is refuted for that action.
- **C-041 — supported**: 0 of 20.
- **C-042 — supported**: 0 of 96 valid (0 of 120 asked), upper bound 3.1%.
- **C-036** stays refuted as written and is superseded by C-040 and C-041.

## 6. What this cannot show

One fictional lab, statements written for the test, one model. Recall is
tested with one question ("What do you know about my plans?"); a sharper
question might surface more. The upper bounds are what 20–96 runs buy.
