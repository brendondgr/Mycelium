# EXP-2026-11-023 — Issues

- **Dirty tree at scaffold time.** `code.dirty: true` because other agents had
  untracked files under other experiments (`EXP-2026-11-017`, `-019`, `-022`)
  that night. None of them is product code. The run used a `git archive` of the
  recorded commit, so the code under test is exactly that commit.
- **Author-record problems, for the maintainer to confirm** (details, with the
  OpenAlex ids, in the private notes):
  - two faculty records are **conflated** with other authors of the same name
    (papers on unrelated subjects among the 50 most-cited works); both were
    imported as they are, because that is what the product does with the record
    an operator picks. Their suggestions may rest on papers that are not theirs;
  - one of those two people's own papers are also **split** over several other
    records, which were not imported;
  - one faculty member is listed in OpenAlex under a longer form of their name
    (verified by four titles);
  - one faculty member joined the institution in August 2026 and their record
    has no affiliation with it yet (verified by three titles);
  - of the 10 student stand-ins, **4** had a record that met the pre-registered
    rule and were imported; 3 had a candidate record that failed it (two
    conflated, one on unrelated topics) and 3 had none.
- **One faculty member's account predates the stand-ins** and is unverified, so
  it could not search. It was not modified; a copy-only stand-in with its
  declared interests was made in the copy (PROTOCOL.md, Data).
- **Mylo turn per professor: not run.** Mylo reaches the matcher only through
  `knowledge_people_beyond_lab`, which needs a funding call
  (`matcher.query_for_call`); a free-text "who should I collaborate with on X"
  has no path to the matcher through Mylo. Attaching an invented call to each
  professor would test something else, so it was skipped.
- **The relay endpoint is shared with live use**; latencies in the logs are not
  a performance measurement.
- **Rating page: one rating per (seeker, candidate), not per row** (found
  2026-11-19 while scoring). The page named each row's radio group
  `r_<seeker>_<candidate>`. One seeker had two people on two rows each (an
  in-field row and a method-bridge row), so each pair of rows shared one radio
  group and one stored rating. The maintainer reported that the page "glitched";
  this is the likely cause. Scoring therefore counts seeker–candidate pairs
  (50), not rows (52). No row was left without a rating.
- **The rating notes stay private.** The free-text notes name or describe real
  people and are kept with the maintainer. The record holds only whether a note
  was written, plus paraphrases without names in RESULTS.md.
