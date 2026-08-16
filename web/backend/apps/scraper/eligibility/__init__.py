"""Provider-agnostic fellowship eligibility helpers.

Two independent things a fellowship record's raw fields cannot express on
their own:

* :mod:`.constraints` — deterministic prose -> constraint extraction. A
  fellowship's structured facets (career-stage checkboxes, a degree dropdown)
  cannot carry a sentence like "must have received the PhD within the
  previous 24 months"; this module reads that sentence out of
  ``metadata["eligibility"]`` so the gate in
  :func:`apps.content.fellowships._constraint_gates` has something to read.
* :mod:`.parsers` — facet vocabularies, deadline/amount parsing, and the
  ``deadline_status`` helper. Provider-agnostic: any source that produces the
  same shaped dict (categories string, deadline label, amount string) can
  reuse it.

Neither module talks to the database or the network, and neither is coupled
to any one source — :mod:`apps.scraper.fellowships.illinois` is the only
current producer of the records these modules read, but nothing here assumes
that.
"""

from __future__ import annotations
