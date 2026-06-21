from django.contrib import admin

from .models import Seat, Subscription


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0
    autocomplete_fields = ("member",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tier", "scope_type", "status", "created_at")
    list_filter = ("tier", "status")
    inlines = (SeatInline,)


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("member", "subscription", "payer_type", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("member__username",)
