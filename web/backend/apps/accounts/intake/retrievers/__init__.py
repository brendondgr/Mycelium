"""Source retrievers: external author id -> raw payload.

OpenAlex and Semantic Scholar use stdlib ``urllib`` with an injectable ``fetch``
(mirroring ``apps/grants`` retrievers and the LLM client). Google Scholar lazily
imports the optional ``scholarly`` package. None of these are exercised by the
test suite — normalizers are tested against canned fixtures, so no test hits the
network.
"""
