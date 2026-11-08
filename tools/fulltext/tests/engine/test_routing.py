from tools.fulltext.engine.routing import explain, humanise, plan, publisher_of

ORDER = [
    "pmc",
    "europepmc",
    "elsevier",
    "springer",
    "wiley",
    "arxiv",
    "unpaywall",
    "openalex",
    "crossref",
    "core",
    "semanticscholar",
]


def route(doi, pmcid=None, pmid="1", disabled=None):
    return {s["source"]: s for s in plan(disabled or {}, pmid, doi, pmcid, ORDER)}


def test_publisher_from_prefix():
    assert publisher_of("10.1016/j.x") == ("Elsevier", "elsevier")
    assert publisher_of("10.1111/x") == ("Wiley", "wiley")
    assert publisher_of("10.1038/s41586") == ("Springer Nature", "springer")
    assert publisher_of("10.1021/acs.est") == ("American Chemical Society", None)
    assert publisher_of(None) == (None, None)


def test_only_the_owning_publisher_api_is_tried():
    r = route("10.1016/j.envpol.2020.111")
    assert r["elsevier"]["action"] == "try"
    assert r["wiley"]["action"] == "skip" and "Elsevier" in r["wiley"]["reason"]
    assert r["springer"]["action"] == "skip"
    assert r["pmc"]["action"] == "skip"
    assert all(
        r[s]["action"] == "try" for s in ("unpaywall", "openalex", "crossref", "core")
    )


def test_pmc_first_when_deposited_and_no_doi_limits_sources():
    r = route(None, pmcid="PMC1")
    assert r["pmc"]["action"] == "try" and r["europepmc"]["action"] == "try"
    assert all(r[s]["action"] == "skip" for s in ("elsevier", "unpaywall", "core"))


def test_disabled_source_is_skipped_with_its_reason():
    r = route(
        "10.1002/x",
        disabled={
            "wiley": "provider quota exhausted (HTTP 500)",
            "core": "missing CORE_API_KEY",
        },
    )
    assert r["wiley"]["action"] == "skip" and "quota" in r["wiley"]["reason"]
    assert r["core"]["reason"] == "missing CORE_API_KEY"


def test_explain_elsevier_entitlement():
    steps = list(route("10.1016/x").values())
    why, retry, nxt = explain(
        "Elsevier",
        "elsevier",
        steps,
        {"elsevier": "http 403 (key valid ...)", "unpaywall": "closed"},
    )
    assert "not entitled" in why and "no legal open-access copy" in why
    assert retry is False and "library" in nxt[0]


def test_explain_wiley_quota_is_retryable():
    steps = list(
        route(
            "10.1002/x", disabled={"wiley": "provider quota exhausted (HTTP 500)"}
        ).values()
    )
    why, retry, nxt = explain("Wiley", "wiley", steps, {"unpaywall": "closed"})
    assert retry is True and "quota" in why and "retry" in nxt[0]


def test_explain_unconfigured_publisher_says_an_operator_can_add_a_key():
    steps = list(
        route("10.1002/x", disabled={"wiley": "missing WILEY_TDM_TOKEN"}).values()
    )
    why, retry, nxt = explain("Wiley", "wiley", steps, {"unpaywall": "closed"})
    assert "missing WILEY_TDM_TOKEN" in why and not retry
    assert "operator" in nxt[0]


def test_explain_publisher_without_api():
    steps = list(route("10.1021/acs.est.1").values())
    why, retry, _ = explain(
        "American Chemical Society", None, steps, {"unpaywall": "closed"}
    )
    assert "no self-serve text-mining API" in why and not retry


def test_humanise_hides_internal_codes():
    assert humanise("closed (cached)") == "knows no open-access copy"
    assert humanise("http 404; no-body (html)") == (
        "does not hold this article (HTTP 404), "
        "returned a page without the article text"
    )
    assert humanise("weird thing") == "weird thing"
    assert humanise("http 400") == "answered HTTP 400"


def test_explain_elsevier_400_view_refusal_is_an_entitlement_problem():
    steps = list(route("10.1016/x").values())
    why, retry, nxt = explain(
        "Elsevier",
        "elsevier",
        steps,
        {
            "elsevier": "http 400 (FULL view refused: key not entitled to full "
            "text from this network/agreement)"
        },
    )
    assert "not entitled" in why and not retry and "library" in nxt[0]
