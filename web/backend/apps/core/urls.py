from django.urls import path

from .views import health

urlpatterns = [
    path("health/", health, name="health"),
    # No-slash variant: a dev proxy may strip the trailing slash before it
    # reaches Django, which would otherwise 301-redirect (see auth endpoints).
    path("health", health, name="health-no-slash"),
]
