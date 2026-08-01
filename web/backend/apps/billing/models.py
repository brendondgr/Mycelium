import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

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
        # The created state for an org (lab/department) plan: the structure exists
        # but the paid plan grants nothing until an explicit activation step. Personal
        # plans skip this — they are created ACTIVE (Free is the ACTIVE baseline).
        INACTIVE = "inactive", "Inactive"
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
    # When set, the plan stops granting entitlements once this instant passes —
    # the read path treats an expired subscription as if it were not there, so a
    # timed grant (e.g. an admin-assigned 90-day Spore) reverts to Free on its own
    # with no cleanup job. Null means "no expiry" (the default open-ended plan).
    # Expiry NEVER deletes data (topics, saves): it only changes what is unlocked,
    # mirroring the no-data-loss downgrade behaviour.
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the plan stops granting entitlements; null = no expiry.",
    )
    # Billing lifecycle (lab/department plans). An org plan is created INACTIVE and
    # carries no period until a PI/head activates it; activation stamps ``activated_at``
    # and opens the first ``[current_period_start, current_period_end)`` window. The
    # period is date-granular (monthly), which is all seat-based proration needs.
    activated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this plan was first activated; null while inactive.",
    )
    current_period_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start of the current billing period; set on activation.",
    )
    current_period_end = models.DateField(
        null=True,
        blank=True,
        help_text="End (exclusive) of the current billing period.",
    )
    billing_interval = models.CharField(
        max_length=20,
        default="monthly",
        help_text="Billing cadence; monthly for now.",
    )
    # A complimentary plan: fully entitled, never charged. Set when a platform admin
    # grants an org plan that never ends (admin dashboard: "Never — complimentary"),
    # which is the durable discriminator the read surfaces need — a PI who activates
    # their own lab also leaves ``expires_at`` null, so a null expiry alone cannot
    # mean "free". Purely a *pricing* statement: entitlements are unaffected, and the
    # plan page renders the seat price struck through.
    is_comped = models.BooleanField(
        default=False,
        help_text="Complimentary plan — entitled but never billed.",
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
        # A tier names who it covers, so it belongs to a scope: Free/Spore cover one
        # researcher, Lab covers a roster, Canopy a department. Deliberately not a DB
        # constraint — see apps.billing.tiers for why.
        from .tiers import TierScopeError, validate_tier_for_scope

        try:
            validate_tier_for_scope(self.scope_type, self.tier)
        except TierScopeError as exc:
            raise ValidationError({"tier": str(exc)}) from exc

    def is_current(self, *, now=None) -> bool:
        """True when this subscription is ACTIVE and not past its expiry."""
        if self.status != Subscription.Status.ACTIVE:
            return False
        if self.expires_at is None:
            return True
        return self.expires_at > (now or timezone.now())

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
    # Scheduled access/billing cutoff for a *deferred* removal. When a member is
    # removed mid-cycle the seat stays ACTIVE (entitled + billed) until this date,
    # then a billing tick flips it to REVOKED — "keep access until end of the current
    # period, no refund" (decision L3). Null = no scheduled removal.
    ends_at = models.DateField(
        null=True,
        blank=True,
        help_text="Deferred-removal cutoff; seat stays ACTIVE until a tick revokes it.",
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


class SeatEvent(models.Model):
    """Append-only billing-math ledger for one seat lifecycle change (decision B6).

    Records every add / activation / removal / expiry with the date it takes effect
    and the prorated amount attributed to it for the current period. This is the audit
    trail behind seat-based billing and the seam a future payment processor would read;
    it is never charged here and never mutated after write. Cents are informational,
    mirroring :class:`AddOn.price_cents`.
    """

    class Kind(models.TextChoices):
        ADDED = "added", "Added"
        ACTIVATED = "activated", "Activated"
        REMOVED = "removed", "Removed"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    effective_date = models.DateField()
    prorated_cents = models.PositiveIntegerField(
        default=0,
        help_text="Amount attributed to this event this period (never charged).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} {self.seat_id} @ {self.effective_date}"


class AddOn(models.Model):
    """A purchasable capability that is orthogonal to tier (architecture A4).

    An add-on grants exactly one :class:`~apps.billing.entitlements.Feature` on
    top of whatever the subscription's tier already unlocks — e.g. the Mylo-server
    add-on grants ``Feature.BOT_SERVER``, which no tier grants on its own. Prices
    are recorded for display only; charging is a Stripe (P7) concern.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    feature = models.CharField(
        max_length=50,
        help_text="The Feature string this add-on grants (e.g. 'bot_server').",
    )
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(
        default=0, help_text="Informational monthly price; billing is deferred."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class SubscriptionAddOn(models.Model):
    """An add-on attached to one subscription — the grant that makes it real.

    Folding an add-on's feature into a tier would corrupt the model (A4); instead
    the union of a covering subscription's active add-ons layers on top of its tier
    features in :func:`~apps.billing.entitlements.effective_features`.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="addons",
    )
    add_on = models.ForeignKey(
        AddOn,
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
            models.UniqueConstraint(
                fields=["subscription", "add_on"],
                name="billing_unique_subscription_addon",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.add_on.slug} on {self.subscription_id} — {self.status}"
