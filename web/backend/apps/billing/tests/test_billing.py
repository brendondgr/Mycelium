import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.accounts.models import Department, Lab
from apps.billing.models import Seat, Subscription, Tier


@pytest.fixture
def owner(db: None) -> User:
    return User.objects.create_user(username="owner", password="pass-123")


@pytest.fixture
def member(db: None) -> User:
    return User.objects.create_user(username="member", password="pass-123")


@pytest.fixture
def department(owner: User) -> Department:
    return Department.objects.create(owner=owner, name="Neuroscience")


@pytest.mark.django_db
def test_spore_subscription_self_paid(member: User) -> None:
    sub = Subscription.objects.create(tier=Tier.SPORE, scope_user=member)
    seat = Seat.objects.create(subscription=sub, member=member, payer_user=member)

    assert sub.scope_type == "user"
    assert sub.scope == member
    assert seat.payer_type == "self"
    assert seat.payer == member


@pytest.mark.django_db
def test_subscription_requires_exactly_one_scope(
    member: User, department: Department
) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Subscription.objects.create(
            tier=Tier.CANOPY, scope_user=member, scope_department=department
        )


@pytest.mark.django_db
def test_subscription_rejects_no_scope() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Subscription.objects.create(tier=Tier.FREE)


@pytest.mark.django_db
def test_canopy_mixes_payers(department: Department, member: User) -> None:
    lab = Lab.objects.create(
        name="Forest Lab", slug="forest-lab", department=department
    )
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)

    self_paid = Seat.objects.create(subscription=sub, member=member, payer_user=member)
    lab_paid = Seat.objects.create(
        subscription=sub,
        member=User.objects.create_user(username="m2", password="p"),
        payer_lab=lab,
    )
    dept_paid = Seat.objects.create(
        subscription=sub,
        member=User.objects.create_user(username="m3", password="p"),
        payer_department=department,
    )

    assert {self_paid.payer_type, lab_paid.payer_type, dept_paid.payer_type} == {
        "self",
        "lab",
        "department",
    }
    assert sub.seats.count() == 3


@pytest.mark.django_db
def test_seat_requires_exactly_one_payer(member: User, department: Department) -> None:
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)
    with pytest.raises(IntegrityError), transaction.atomic():
        Seat.objects.create(
            subscription=sub,
            member=member,
            payer_user=member,
            payer_department=department,
        )


@pytest.mark.django_db
def test_member_has_one_seat_per_subscription(
    member: User, department: Department
) -> None:
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)
    Seat.objects.create(subscription=sub, member=member, payer_department=department)

    with pytest.raises(IntegrityError), transaction.atomic():
        Seat.objects.create(subscription=sub, member=member, payer_user=member)
