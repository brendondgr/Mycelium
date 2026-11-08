"""``GET /api/tools/`` — which tools this instance runs.

Any signed-in user sees each tool's name, summary and state (the frontend uses
it to show only what is available). Staff also see why a tool is not loaded.
"""

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tools_status(request):
    report = settings.TOOLS_REPORT
    staff = bool(request.user.is_staff)
    rows = []
    for name in report.order:
        item = report.tools[name]
        row = {
            "name": name,
            "summary": item.summary,
            "state": item.state,
            "core": item.core,
            "depends_on": item.depends_on,
        }
        if staff:
            row["reason"] = item.reason
        rows.append(row)
    return Response({"tools": rows})
