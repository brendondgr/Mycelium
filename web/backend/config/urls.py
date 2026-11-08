from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from tools._framework.host import splice_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.research.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.billing.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
    path("api/admin/", include("apps.adminpanel.urls")),
    path("api/ambient/", include("apps.ambient.urls")),
    path("api/collab/", include("apps.collab.urls")),
    path("api/", include("tools._framework.urls")),
]

# Loaded tools' routes, each spliced in after the platform include it names —
# URL order is resolution order, and a golden test holds the table unchanged.
urlpatterns = splice_urls(urlpatterns, settings.TOOLS_URL_MOUNTS)
