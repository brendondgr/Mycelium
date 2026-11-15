# Calibration sheet — how to mark it

About 30 minutes. Each row of `calibration.csv` is one answer a research
assistant gave. Open its `evidence_file`: it shows the question, the answer and
**the evidence the assistant had**. The lab is fictional; the items are real.

Judge only against the evidence shown, never against outside knowledge. If you
cannot tell from the evidence whether a detail is true, treat it as
unsupported.

Fill in:

1. `n_details` — how many stated details the answer contains (an author,
   venue, date, year, amount, number, name, or a specific finding or property
   claimed about an item, project or person; citation markers like `#3` are
   not details).
2. `unsupported_details` — every detail you cannot find in the evidence,
   separated by `;`, each followed by its kind in brackets: `[fact_line]` (on a
   `Label: value` line), `[figure]` (a number or amount in a sentence),
   `[sentence]` (another specific value in a sentence), `[claim]` (a
   statement with no number). Leave empty if none.
3. `notes` — optional.

Mark each answer on its own. An automatic reader marked the same answers; its
marks are kept outside this folder until you finish.
