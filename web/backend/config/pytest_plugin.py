"""Suite-wide defaults, loaded as a pytest plugin (``-p config.pytest_plugin``).

A plugin rather than ``web/backend/conftest.py`` because a conftest only
reaches tests below its own folder, and the tools' tests live in ``tools/`` at
the repository root. Every test — platform or tool — gets these fixtures.

**Why the suite enforces entitlements when the deployment does not.**

``BILLING_ENFORCE_ENTITLEMENTS`` ships off, so a running Mycelium currently grants
every capability to everyone (see ``apps.billing.entitlements.enforcing``). The tier
matrix is still the product's contract, though, and this suite is the only place that
contract is written down and checked. Running the tests under the deployment's
temporary default would have meant deleting or inverting roughly fifty entitlement
tests — and then turning the switch back on would be a change with no test coverage
standing behind it.

So billing and gating are **on** here (the ``institution`` profile), which is
exactly the behaviour every one of those tests was written against. Tests about the
switch itself opt out explicitly with
``override_settings(BILLING_ENFORCE_ENTITLEMENTS=False)``; see
``apps/billing/tests/test_entitlement_switch.py``.
"""

import os
from pathlib import Path

import pytest

# A tool that fails to load fails the suite (tools.strict) rather than being
# silently set aside, so a broken tool can never produce a green run. Set before
# pytest-django configures Django, which is when settings.py boots the tools.
os.environ.setdefault("MYCELIUM_TOOLS_STRICT", "1")

from config import instance

# The suite runs against the ``institution`` profile — the subscription-era
# behaviour every billing, cap and entitlement test was written for — resolved
# with no file and no environment, so a developer's own mycelium.toml or .env
# never changes a result. Tests about billing being off (the default profile)
# opt out with the ``billing_off`` fixture below.
_SUITE = instance.resolve(
    Path("/nonexistent"), {}, file_values={"instance.profile": "institution"}
)


def _limits(cfg):
    flat = {
        key.removeprefix("limits."): value
        for key, value in cfg.values.items()
        if key.startswith("limits.") and not key.startswith("limits.tiers.")
    }
    tiers: dict = {}
    for key, value in cfg.values.items():
        if key.startswith("limits.tiers."):
            tier, name = key.removeprefix("limits.tiers.").split(".")
            tiers.setdefault(tier, {})[name] = value
    return flat, tiers


@pytest.fixture(autouse=True)
def _enforce_entitlements(settings):
    """Pin billing on and tier gating on for every test, whatever the deployment
    configures."""
    flat, tiers = _limits(_SUITE)
    settings.BILLING_MODE = "subscriptions"
    settings.BILLING_ENABLED = True
    settings.INSTANCE_LIMITS = flat
    settings.INSTANCE_TIER_LIMITS = tiers
    settings.BILLING_ENFORCE_ENTITLEMENTS = True


@pytest.fixture(autouse=True)
def _institution_signup(settings):
    """Sign-up as the institution profile has it: a shared code, verified email.

    The code is pinned here because a fresh clone has none — there is no default
    code any more, by design."""
    settings.SIGNUP_MODE = _SUITE["signup.mode"]
    settings.SIGNUP_VERIFY_EMAIL = _SUITE["signup.verify_email"]
    settings.SIGNUP_ALLOWED_DOMAINS = []
    settings.SIGNUP_ACCESS_CODE = "test-signup-code"


@pytest.fixture
def billing_off(settings):
    """Run one test as a default (``lab``) instance: no billing, no limits."""
    cfg = instance.resolve(Path("/nonexistent"), {}, file_values={})
    flat, tiers = _limits(cfg)
    settings.BILLING_MODE = "off"
    settings.BILLING_ENABLED = False
    settings.INSTANCE_LIMITS = flat
    settings.INSTANCE_TIER_LIMITS = tiers
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    return settings


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
    """Pin the decision backend to ``off`` for every test.

    The deployment default is ``auto``, and with a key or port URL in the
    environment the stage would make real calls from worker threads inside a
    pipeline test — which is how 20 ledger rows once leaked out of
    ``test_every_theme_reaches_the_model``. Tests about the switch set a backend
    explicitly and pass a fake client.
    """
    settings.DECISION_BACKEND = "off"


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
