# EXP-2026-09-017 — Issues

## Run 1 — registered (3955910): 11 violations, all in the harness

The routing check matched a change's topic as a substring of a report row.

- **8 "duplicated"**: every Lab B member's weekly holds two rows containing
  "annotation budget". One is the stated-state edit "(annotation budget)"; the
  other is the told fact "the annotation budget came through". These are two
  different changes, each shown once.
- **3 "leaked"**: amb_c4_ines's row "Project C1 dataset arrival" (her own
  personal told fact) contains "Project C1 dataset" (personal told facts of
  amb_c1_umar and amb_c3_nia). amb_c5_elin's row "Project C2 dataset
  arrival" contains amb_c2_oren's "Project C2 dataset". The change table
  confirms each row is the reader's own.

Fixed in the harness (2babb96): a row is about a topic only when the topic
fills its slot in the row (`**topic** —`, `— topic —`, `(topic) —`).

Found in the feature at the same time: an undo of a change from the same week
showed as its own row ("undone on Sat 19 Sep") beside the change's "(since
undone)". It is now the mark only (2babb96, with a test). The harness was
updated to expect that.

## Run 2 (2babb96)

0 violations. Both runs start from a fresh copy of `mycelium_sandbox_ambweb`.

## Not exercised

The sandbox people have no scored feed items, so every project section in
every weekly is the deterministic fallback. The model was called only for
the overview, and no model sentence cited `[O#]`. H2's exploratory half
(how the model links an item to a change) is unmeasured.
