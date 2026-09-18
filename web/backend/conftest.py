"""Suite-wide defaults.

**Why the suite enforces entitlements when the deployment does not.**

``BILLING_ENFORCE_ENTITLEMENTS`` ships off, so a running Mycelium currently grants
every capability to everyone (see ``apps.billing.entitlements.enforcing``). The tier
matrix is still the product's contract, though, and this suite is the only place that
contract is written down and checked. Running the tests under the deployment's
temporary default would have meant deleting or inverting roughly fifty entitlement
tests — and then turning the switch back on would be a change with no test coverage
standing behind it.

So gating is **on** here, which is exactly the behaviour every one of those tests was
written against. Tests about the switch itself opt out explicitly with
``override_settings(BILLING_ENFORCE_ENTITLEMENTS=False)``; see
``apps/billing/tests/test_entitlement_switch.py``.
"""

import pytest


@pytest.fixture(autouse=True)
def _enforce_entitlements(settings):
    """Pin tier gating on for every test, whatever the deployment default is."""
    settings.BILLING_ENFORCE_ENTITLEMENTS = True


@pytest.fixture(autouse=True)
def _serial_llm_calls(settings):
    """Keep the write-up and opportunity scorers on the test thread.

    A worker thread opens its own database connection, so anything it writes —
    the LLM ledger row a failed call records, for one — commits outside the test
    transaction and leaks into the next test. Serial here; tests about the
    parallel path set these (or pass ``concurrency=``) explicitly.
    """
    settings.WRITEUP_LLM_CONCURRENCY = 1
    settings.OPPORTUNITY_LLM_CONCURRENCY = 1


@pytest.fixture(autouse=True)
def _local_rerank(settings):
    """Pin ``RERANK_METHOD`` to ``local`` for every test.

    The deployment default is ``typesafe``, and with a key in the environment
    the stage would make real, billed calls from worker threads inside a
    pipeline test — which is how 20 ledger rows once leaked out of
    ``test_every_theme_reaches_the_model``. Tests about the switch set
    ``typesafe`` explicitly and pass a fake client.
    """
    settings.RERANK_METHOD = "local"


@pytest.fixture(autouse=True)
def _no_knowledge_projection_on_save(settings):
    """Keep the knowledge core's save and import hooks from queueing Celery tasks.

    The hook runs on commit, which a transactional test really does reach — and
    then ``.delay()`` would hand a test-database id to whatever worker listens
    on the broker. The knowledge-core tests that exercise the hook turn it back
    on and capture the task instead.
    """
    settings.KNOWLEDGE_PROJECT_ON_SAVE = False
    settings.KNOWLEDGE_FACET_ON_IMPORT = False
