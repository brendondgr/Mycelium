# EXP-2026-09-016 — Issues

## Run 1 — registered harness (fcfe239)

Failures in the feature:

1. **The answer's reply disappears.** The card held the reply in local state,
   and the answered question drops out of the refetched list, so no reply was
   ever visible. Fixed in 1f181c5: the reply is kept in a `role=status` live
   region above the list.
2. **Colour contrast** (axe `color-contrast`, serious, every Mylo & you tab
   and the profile's "heard" chip):
   - `--text-muted` #7f8775 gives 3.03–3.67:1;
   - the shared tab bar's active label #5e7a3e on its tint gives 4.05:1.

   Fixed in 1f181c5: the ambient components use `--text-secondary`, and the tab
   bar's active label uses `--brand-primary-hover`.
3. **Repeated names** (reported, no bar): five "Undo", three "Edit" and three
   "Delete". Now named for their topic.

Failure in the data: the lab overview showed the setup form because the
sandbox lab had no profile, so the lab's "What changed" card could not appear.
`prep.py` now plants a lab statement (listed in `prep.json`). This was added
after run 1.

## Run 2 (1f181c5)

Failures in the feature:

1. **A first entry could not be undone.** The applied edit's `old_value` was
   `{"learning_goals": null}`. Restoring `null` was refused by
   `validate_interests`, so the API returned 400 (that was also the console
   error). Fixed in bf94544: a field that did not exist before is removed, and
   the edit's row in `sources.ambient` goes with it. Tests cover all four fields.
2. **Filing words stored as a rename.** Carried in from EXP-2026-09-015 run 4:
   "things I'm picking up" was stored as a correction and written as a learning
   goal, while the bell announced "argument mining". Fixed in bf94544:
   - reader r5 forbids filing words in a correction;
   - `_echoes_a_choice` drops a correction made only of filing words;
   - the bell uses the written wording.

   The existing row stays in the sandbox data, as history.

Failures in the harness:

- The badge was read before it loaded.
- The bell was counted before its list loaded.
- The focus-visible check compared a live `getComputedStyle` object with
  itself.

## Run 3 (bf94544)

One failure, in the harness. The settings sweep reached 3 of 5 controls
because blurring and refocusing the date input restarts its segments, so Tab
never left it. A manual trace reached all five. Fixed in a9d4ab3.

## Run 4 (a9d4ab3)

No failures. 67 seconds for both passes.
