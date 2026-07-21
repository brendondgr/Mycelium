from django.urls import path

from .views import (
    DeptBillingActivateView,
    DeptBillingView,
    EntitlementsView,
    LabBillingActivateView,
    LabBillingView,
)

urlpatterns = [
    path("billing/me/", EntitlementsView.as_view(), name="billing-me"),
    # Lab plan state + activation (slash + no-slash so the dev proxy can POST).
    path("labs/<slug:slug>/billing/", LabBillingView.as_view(), name="lab-billing"),
    path("labs/<slug:slug>/billing", LabBillingView.as_view()),
    path(
        "labs/<slug:slug>/billing/activate/",
        LabBillingActivateView.as_view(),
        name="lab-billing-activate",
    ),
    path("labs/<slug:slug>/billing/activate", LabBillingActivateView.as_view()),
    # Department plan state + activation.
    path(
        "departments/<uuid:pk>/billing/",
        DeptBillingView.as_view(),
        name="dept-billing",
    ),
    path("departments/<uuid:pk>/billing", DeptBillingView.as_view()),
    path(
        "departments/<uuid:pk>/billing/activate/",
        DeptBillingActivateView.as_view(),
        name="dept-billing-activate",
    ),
    path(
        "departments/<uuid:pk>/billing/activate",
        DeptBillingActivateView.as_view(),
    ),
]
