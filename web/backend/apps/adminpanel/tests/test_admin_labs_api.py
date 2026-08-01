"""Admin dashboard API — the Labs management context.

Proves the same gate covers labs, and that a lab PATCH lands where it has to: the tier
and status flow through the shared activation service (so members get seated and the
entitlement read path lights up), a never-ending complimentary plan zeroes the recurring
total while keeping the list price readable, and the Mylo toggle actually grants/revokes
the ``bot_server`` add-on the Discord setup path gates on.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent, Lab, LabMembership
from apps.billing.addons import mylo_included
from apps.billing.entitlements import Feature, effective_tier, lab_has_feature
from apps.billing.models import Seat, Subscription, Tier
from apps.billing.pricing import recurring_monthly_cents, seat_price_cents

LIST_URL = "/api/admin/labs/"


def detail_url(lab: Lab) -> str:
    return f"/api/admin/labs/{lab.slug}/"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def superuser() -> User:
    return User.objects.create_superuser(username="root", password="p")


@pytest.fixture
def member() -> User:
    return User.objects.create_user(username="regular", password="p")


@pytest.fixture
def lab(member: User) -> Lab:
    """A lab as provisioning leaves it: INACTIVE plan, PENDING founder seat."""
    lab = Lab.objects.create(name="Mycelium Lab", slug="mycelium-lab")
    LabMembership.objects.create(
        user=member, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    sub = Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.INACTIVE
    )
    Seat.objects.create(
        subscription=sub, member=member, payer_lab=lab, status=Seat.Status.PENDING
    )
    return lab


# -- permission gate -----------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_is_blocked(client: APIClient, lab: Lab) -> None:
    assert client.get(LIST_URL).status_code in (401, 403)
    assert client.get(detail_url(lab)).status_code in (401, 403)


@pytest.mark.django_db
def test_regular_user_forbidden(client: APIClient, member: User, lab: Lab) -> None:
    client.force_authenticate(member)
    assert client.get(LIST_URL).status_code == 403
    assert client.get(detail_url(lab)).status_code == 403
    assert (
        client.patch(detail_url(lab), {"tier": Tier.CANOPY}, format="json").status_code
        == 403
    )


# -- listing -------------------------------------------------------------------


@pytest.mark.django_db
def test_row_shape_and_search(client: APIClient, superuser: User, lab: Lab) -> None:
    Lab.objects.create(name="Unrelated Group", slug="unrelated-group")
    client.force_authenticate(superuser)

    body = client.get(LIST_URL, {"q": "mycelium"}).data
    assert [row["slug"] for row in body["results"]] == [lab.slug]

    row = body["results"][0]
    assert row["member_count"] == 1
    assert row["subscription"]["tier"] == Tier.LAB
    assert row["subscription"]["status"] == Subscription.Status.INACTIVE
    assert row["subscription"]["mylo_included"] is False
    assert row["subscription"]["is_comped"] is False


@pytest.mark.django_db
def test_lab_without_a_plan_still_lists(client: APIClient, superuser: User) -> None:
    Lab.objects.create(name="Planless", slug="planless")
    client.force_authenticate(superuser)
    row = client.get(LIST_URL, {"q": "planless"}).data["results"][0]
    assert row["subscription"] is None


# -- writes: activation --------------------------------------------------------


@pytest.mark.django_db
def test_activation_seats_members_and_grants_entitlements(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    assert effective_tier(member) == Tier.FREE  # inactive plan grants nothing

    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(lab), {"status": Subscription.Status.ACTIVE}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["subscription"]["status"] == Subscription.Status.ACTIVE

    sub = Subscription.objects.get(scope_lab=lab)
    assert sub.activated_at is not None
    assert sub.current_period_end is not None
    assert (
        Seat.objects.get(subscription=sub, member=member).status == Seat.Status.ACTIVE
    )
    assert effective_tier(member) == Tier.LAB
    assert AuditEvent.objects.filter(action="admin.lab_subscription.assign").exists()


@pytest.mark.django_db
def test_tier_is_applied_before_activation(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(lab),
        {"tier": Tier.CANOPY, "status": Subscription.Status.ACTIVE},
        format="json",
    )
    assert resp.status_code == 200
    assert effective_tier(member) == Tier.CANOPY


@pytest.mark.django_db
def test_deactivation_revokes_entitlements(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    client.patch(detail_url(lab), {"status": Subscription.Status.ACTIVE}, format="json")
    assert effective_tier(member) == Tier.LAB

    client.patch(
        detail_url(lab), {"status": Subscription.Status.CANCELED}, format="json"
    )
    assert effective_tier(member) == Tier.FREE


# -- writes: how the plan ends -------------------------------------------------


@pytest.mark.django_db
def test_duration_sets_expiry_and_lapses_via_the_read_path(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(lab),
        {"status": Subscription.Status.ACTIVE, "duration_days": 30},
        format="json",
    )
    assert resp.status_code == 200
    sub = Subscription.objects.get(scope_lab=lab)
    assert sub.expires_at is not None
    expected = timezone.now() + timedelta(days=30)
    assert abs((sub.expires_at - expected).total_seconds()) < 60
    assert effective_tier(member) == Tier.LAB

    # Backdate the expiry: entitlements drop away with no cleanup job, nothing deleted.
    client.patch(
        detail_url(lab),
        {"expires_at": (timezone.now() - timedelta(days=1)).isoformat()},
        format="json",
    )
    assert effective_tier(member) == Tier.FREE
    assert Subscription.objects.get(scope_lab=lab).tier == Tier.LAB


@pytest.mark.django_db
def test_comped_lab_is_entitled_but_free(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(lab),
        {
            "status": Subscription.Status.ACTIVE,
            "duration_days": None,
            "is_comped": True,
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["subscription"]["is_comped"] is True
    assert resp.data["subscription"]["expires_at"] is None

    sub = Subscription.objects.get(scope_lab=lab)
    # Fully entitled, never billed — and the list price stays readable so the plan
    # page can strike it through rather than hide it.
    assert effective_tier(member) == Tier.LAB
    assert recurring_monthly_cents(sub) == 0
    assert seat_price_cents(sub.tier) > 0


@pytest.mark.django_db
def test_lab_billing_payload_reports_comped(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    client.patch(
        detail_url(lab),
        {"status": Subscription.Status.ACTIVE, "is_comped": True},
        format="json",
    )

    client.force_authenticate(member)
    body = client.get(f"/api/labs/{lab.slug}/billing/").data
    assert body["is_comped"] is True
    assert body["recurring_monthly_cents"] == 0
    assert body["add_member_proration_cents"] == 0
    assert body["seat_price_cents"] > 0


# -- writes: Mylo inclusion ----------------------------------------------------


@pytest.mark.django_db
def test_mylo_toggle_grants_and_revokes_the_addon(
    client: APIClient, superuser: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    client.patch(detail_url(lab), {"status": Subscription.Status.ACTIVE}, format="json")
    assert not lab_has_feature(lab, Feature.BOT_SERVER)

    on = client.patch(detail_url(lab), {"mylo_included": True}, format="json")
    assert on.status_code == 200
    assert on.data["subscription"]["mylo_included"] is True
    assert lab_has_feature(lab, Feature.BOT_SERVER)

    off = client.patch(detail_url(lab), {"mylo_included": False}, format="json")
    assert off.data["subscription"]["mylo_included"] is False
    assert not lab_has_feature(lab, Feature.BOT_SERVER)
    assert not mylo_included(Subscription.objects.get(scope_lab=lab))


@pytest.mark.django_db
def test_mylo_surfaces_on_the_lab_billing_endpoint(
    client: APIClient, superuser: User, member: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    client.patch(
        detail_url(lab),
        {"status": Subscription.Status.ACTIVE, "mylo_included": True},
        format="json",
    )
    client.force_authenticate(member)
    assert client.get(f"/api/labs/{lab.slug}/billing/").data["mylo_included"] is True


# -- write validation ----------------------------------------------------------


@pytest.mark.django_db
def test_empty_patch_rejected(client: APIClient, superuser: User, lab: Lab) -> None:
    client.force_authenticate(superuser)
    assert client.patch(detail_url(lab), {}, format="json").status_code == 400


@pytest.mark.django_db
def test_duration_and_expires_together_rejected(
    client: APIClient, superuser: User, lab: Lab
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(lab),
        {
            "duration_days": 30,
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_over_ceiling_activation_is_a_400_not_a_500(
    client: APIClient, superuser: User, lab: Lab
) -> None:
    """A roster larger than the chosen tier allows fails honestly, writing nothing."""
    for n in range(3):
        LabMembership.objects.create(
            user=User.objects.create_user(username=f"m{n}", password="p"),
            lab=lab,
            role=LabMembership.Role.MEMBER,
        )
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(lab),
        {"tier": Tier.SPORE, "status": Subscription.Status.ACTIVE},  # Spore ceiling = 1
        format="json",
    )
    assert resp.status_code == 400
    sub = Subscription.objects.get(scope_lab=lab)
    assert sub.status == Subscription.Status.INACTIVE
