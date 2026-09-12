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
