from django.urls import path

from . import views

urlpatterns = [
    # Both forms so a dev proxy that strips the trailing slash still resolves
    # (matches the workspace read endpoints).
    path("daily-report/", views.DailyReportView.as_view(), name="daily-report"),
    path("daily-report", views.DailyReportView.as_view(), name="daily-report-no-slash"),
]
