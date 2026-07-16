from django.contrib import admin

from .models import AddOn, Seat, Subscription, SubscriptionAddOn


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0
    autocomplete_fields = ("member",)


class SubscriptionAddOnInline(admin.TabularInline):
    model = SubscriptionAddOn
    extra = 0
    autocomplete_fields = ("add_on",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tier", "scope_type", "status", "created_at")
    list_filter = ("tier", "status")
    inlines = (SeatInline, SubscriptionAddOnInline)


@admin.register(AddOn)
class AddOnAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "feature", "price_cents")
    search_fields = ("slug", "name", "feature")


@admin.register(SubscriptionAddOn)
class SubscriptionAddOnAdmin(admin.ModelAdmin):
    list_display = ("add_on", "subscription", "status", "created_at")
    list_filter = ("status",)


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("member", "subscription", "payer_type", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("member__username",)
