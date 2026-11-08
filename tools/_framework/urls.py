from django.urls import path

from .views import tools_status

urlpatterns = [
    path("tools/", tools_status, name="tools-status"),
    path("tools", tools_status),
]
