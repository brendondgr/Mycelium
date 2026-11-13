# Rating instructions

Thank you for rating. Plan on about two hours; you can stop and resume.

You will rate answers to questions a lab's principal investigator asked a
research assistant. Each row of `answers_rater<k>.csv` is one answer. Open the
file named in `evidence_file` (in `evidence/`): it shows the question, the
answer, and **the evidence the assistant had in front of it**. The lab is
fictional; the papers, grants and fellowships are real.

**Judge only against the evidence shown, never against outside knowledge.**
If you cannot tell from the evidence whether something is true, treat it as
unsupported.

For each answer fill in:

1. `correct` — `yes`, `partly` or `no`. Does the answer correctly answer the
   question, given the evidence? `partly` means some of it is right and some
   is wrong or missing.
2. `citation_support` — the column lists every citation in the answer as
   `#n=?`. Replace each `?` with `yes` if the evidence item numbered `#n`
   supports the sentence the citation sits on, otherwise `no`. Leave it empty
   if the answer has no citations.
3. `unsupported_details` — list every stated detail (an author, venue, date,
   year, amount, number, or a named finding) that you **cannot find in the
   evidence**, separated by `;`. Leave it empty if there are none.
4. `useful_1to5` — how useful would this answer be to a PI? 1 = useless or
   misleading, 3 = adequate, 5 = exactly what they needed.
5. `notes` — optional.

Rate each answer on its own. Two answers to the same question may appear; do
not compare them.

The second sheet, `removed_rater<k>.csv`, lists details and citations that an
automatic checker flagged in a draft answer, each shown in its sentence. Open
the evidence file and mark `supported` `yes` if the evidence supports that
detail (or, for a citation, if the cited item supports the sentence), `no` if
it does not or you cannot tell.

Please rate independently: do not discuss items with the other raters until
everyone has finished.
