# Fulltext

Gets the paper itself. Given a paper identifier (PMID, PMCID, DOI, arXiv id,
or a PubMed / PMC / doi.org / publisher / arXiv URL), it checks whether a legal
copy can be reached, fetches it, and keeps the original (PDF / JATS XML / HTML)
plus a markdown rendering. It is the read path later tools (the claim-stance
and hypothesis engines in `docs/goals.md`) use to read whole papers instead of
abstracts.

| | |
|---|---|
| Depends on | `retrieval` |
| Exports | `read`, `service`, `events` |
| Config | `[tools.fulltext]` in `mycelium.toml` |
| Nightly stages | — |
| API | — (an API comes later, inside this folder) |

## The engine

`engine/` is plain Python with no Django imports, ported from the
PubMedExtraction project. It resolves every identifier against PubMed, the
arXiv API, Crossref and DataCite before fetching anything (so a PMID and DOI of
different papers stop as `identifier_mismatch` instead of fetching the wrong
one), routes each paper only to the sources that can serve it (a DOI prefix
names its publisher, so Wiley's daily quota is never spent on an Elsevier
paper), and explains every failure in words, with whether retrying can help.

| Module | Does |
|---|---|
| `engine/identifiers.py` | parses identifiers and URLs; no network |
| `engine/resolver.py` | verifies identifiers and fetches metadata; batched PMC efetch |
| `engine/routing.py` | which sources to ask, and the plain-words explanation |
| `engine/fetcher.py` | one method per source; deadlines, quota stops, strike-outs |
| `engine/convert.py` | JATS, Elsevier XML, HTML and PDF to markdown |
| `engine/state.py` | switch-offs, throttles and remembered answers, shareable between workers |
| `engine/cache.py` | the on-disk response cache, one file per key, atomic writes |
| `engine/pipeline.py` | `Engine`: `resolve()`, `fetch()`, `sources()` |
| `engine/probe.py` | the live key check behind `fulltext_sources --check` |

### Sources

| Source | Needs | |
|---|---|---|
| PubMed Central, Europe PMC, arXiv | nothing | always on |
| Unpaywall | a real contact email | on whenever the instance has one |
| OpenAlex, Crossref, CORE, Semantic Scholar | nothing (a key only raises the rate limit) | always on |
| Elsevier, Springer Nature, Wiley | the instance's key | off without one |

Keys belong to the instance, set by its operator; users never enter them.
Elsevier and Wiley authorise by the IP address of the server making the
request, so they only serve subscription content when the instance runs on a
subscribing network. Elsevier additionally needs the library to enable the
full-text Article Retrieval API for the key (or an institutional token).

PDFs convert with `pypdf`, not `pymupdf4llm` (AGPL-3.0, incompatible with
Mycelium's Apache-2.0 licence): plain paragraphs without layout headings. The
original PDF is always kept.

## Configuration

`[tools.fulltext]` in `mycelium.toml` (`make config ARGS="explain tools.fulltext"`):
`sources` (which, in what order), `contact_email` (empty uses
`SCRAPER_CONTACT_EMAIL`), `min_chars`, `concurrency`, `disable_ttl_hours`.

The publisher keys are secrets, set in `.env` only: `ELSEVIER_API_KEY`,
`ELSEVIER_INST_TOKEN`, `SPRINGER_API_KEY`, `WILEY_TDM_TOKEN`, `CORE_API_KEY`.
The PubMed, OpenAlex and Semantic Scholar keys the literature scan already uses
are reused (`config.py` maps settings onto the engine's credential names).

```bash
manage.py fulltext_sources            # what is on, from the configuration alone
manage.py fulltext_sources --check    # ask each keyed provider, live
```

`--check` reports each source as `on`, `off` (no key), `key rejected`,
`key fine, not entitled from this network` (Elsevier: the Search API accepts
the key, the Article Retrieval API does not), `refused: token or network`
(Wiley answers a made-up token and a real token from the wrong network with
the same 403), `quota exhausted`, or `unreachable`.

## Doors

- `read.py` — nothing yet.
- `service.py` — nothing yet.

## Tests

`uv run --directory web/backend pytest -c pyproject.toml ../../tools/fulltext`

The engine tests (`tests/engine/`) need no network and no database.
