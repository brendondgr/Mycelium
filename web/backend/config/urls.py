from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.research.urls")),
    path("api/", include("apps.content.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.billing.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
    path("api/admin/", include("apps.adminpanel.urls")),
    path("api/ambient/", include("apps.ambient.urls")),
    path("api/collab/", include("apps.collab.urls")),
]
