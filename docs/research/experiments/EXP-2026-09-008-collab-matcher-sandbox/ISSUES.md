# EXP-2026-09-008 — Issues

1. **The first world build never finished (recorded, not deleted).** The
   600-person build started 2026-09-18 19:59 ran 35 minutes at full CPU with
   no output: the world generator drew given × family name pairs until it
   found an unused one, and 600 people exceed the pairs available, so the
   draw never ended. No data was written; the database still held the
   240-person world. Fixed in `sandbox/collab/world.py` (`_unique_name`: a
   middle initial once the pairs run out, drawn only then, so every world
   below the limit — including EXP-2026-09-005 to -007's 240 — is unchanged)
   and rebuilt. The `match` command was also missing from the harness's
   command list and would have been refused; added.
