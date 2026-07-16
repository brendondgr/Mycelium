from django.urls import path

from .views import EntitlementsView

urlpatterns = [
    path("billing/me/", EntitlementsView.as_view(), name="billing-me"),
]
