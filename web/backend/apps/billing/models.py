import uuid

from django.conf import settings
from django.db import models

from apps.core.db import exactly_one, validate_exactly_one

SCOPE_FIELDS = ("scope_user", "scope_lab", "scope_department")
PAYER_FIELDS = ("payer_department", "payer_lab", "payer_user")


class Tier(models.TextChoices):
    """Subscription tiers (briefing §7). Structure is free; intelligence is gated."""

    FREE = "free", "Free"
    SPORE = "spore", "Spore"
    LAB = "lab", "Mycelium Lab"
    CANOPY = "canopy", "Canopy"


class Subscription(models.Model):
    """The plan and entitlement for one scope (briefing §3, §7).

    Polymorphic scope: a subscription is for exactly one User, Lab, or
    Department. It holds the *plan*, not a payer — each covered member is a
    :class:`Seat`, and the payer is recorded per seat, so one Canopy department
    can mix payers.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tier = models.CharField(max_length=20, choices=Tier.choices)
    scope_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    scope_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    scope_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="billing_subscription_one_scope",
                condition=exactly_one(*SCOPE_FIELDS),
            ),
        ]

    def clean(self) -> None:
        validate_exactly_one(self, *SCOPE_FIELDS)

    @property
    def scope_type(self) -> str:
        """Derived discriminator: ``user`` / ``lab`` / ``department``."""
        if self.scope_user_id is not None:
            return "user"
        if self.scope_lab_id is not None:
            return "lab"
        return "department"

    @property
    def scope(self):
        return self.scope_user or self.scope_lab or self.scope_department

    def __str__(self) -> str:
        return f"{self.get_tier_display()} ({self.scope_type}) — {self.status}"


class Seat(models.Model):
    """One covered member under a subscription (briefing §3, §7).

    The seat carries the payer, which is what makes flexible Canopy billing
    possible: ``payer_user`` is self-pay, ``payer_lab`` is lab-sponsored,
    ``payer_department`` is department-paid. Seat count = active seats.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="seats",
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seats",
    )
    payer_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="paid_seats",
    )
    payer_lab = models.ForeignKey(
        "accounts.Lab",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="paid_seats",
    )
    payer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="paid_seats",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "member"],
                name="billing_unique_seat_member",
            ),
            models.CheckConstraint(
                name="billing_seat_one_payer",
                condition=exactly_one(*PAYER_FIELDS),
            ),
        ]

    def clean(self) -> None:
        validate_exactly_one(self, *PAYER_FIELDS)

    @property
    def payer_type(self) -> str:
        """Derived discriminator: ``department`` / ``lab`` / ``self``."""
        if self.payer_department_id is not None:
            return "department"
        if self.payer_lab_id is not None:
            return "lab"
        return "self"

    @property
    def payer(self):
        return self.payer_department or self.payer_lab or self.payer_user

    def __str__(self) -> str:
        return f"{self.member} seat ({self.payer_type}-paid, {self.status})"
