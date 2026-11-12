"""Every org-scoped view names the capability each of its methods needs.

A view is org-scoped when its route carries a lab or a department
(``labs/<slug>``, ``lab/<slug>``, ``departments/<uuid>``), or when it is one of
the views below that take the org from the query string or the body. Each must
declare ``capabilities = {METHOD: capability}`` for every method it serves,
naming a capability from the closed list or ``capabilities.MEMBERSHIP``.

A declaration that lies is worse than none, so the second half walks a role
matrix through a sample of these routes and checks that the API refuses exactly
the roles whose preset lacks the declared capability.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import get_resolver, resolve
from django.urls.resolvers import URLPattern, URLResolver
from rest_framework.test import APIClient

from apps.accounts import capabilities as caps
from apps.accounts.models import DeptMembership, LabMembership
from apps.billing.services import create_department_workspace, create_lab_workspace

from .conftest import verified

ORG_IN_PATH = re.compile(r"(^|/)(labs?|departments)/<(slug|uuid):(slug|pk)>")
NOT_WORKSPACE = ("admin/", "api/admin/")  # Django admin and the staff panel

#: Views that take the org from ``?lab=`` / ``?department=`` or the body.
ORG_FROM_REQUEST = {
    "AnnouncementsView",
    "AnnouncementSettingsView",
    "AnnouncementTestView",
    "AnnouncementCreateChannelsView",
    "DepartmentOpportunitiesView",
    "DiscordLabActivationCodeView",
    "DiscordDepartmentActivationCodeView",
    "DiscordBindingRemoveView",
    "SlackLabCodeView",
    "TeamsLabCodeView",
    "TeamsLabView",
    "LabMentionTargetsView",
    "LabReminderChannelsView",
    "PolicyView",  # Mylo's policy: /policy/<lab|department>/<ref>/
    # Personal by default, an org's when the request names one:
    "ProjectListView",
    "ReminderListCreateView",
    "ReminderAccessView",
    "SaveOpportunityView",
    "TranscriptUploadView",
}

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
ALLOWED = set(caps.CAPABILITIES) | {caps.MEMBERSHIP}


def _routes() -> list[tuple[str, type]]:
    out: list[tuple[str, type]] = []

    def walk(patterns, prefix: str) -> None:
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                cb = p.callback
                view = getattr(cb, "view_class", None) or getattr(cb, "cls", None)
                if view is not None:
                    out.append((prefix + str(p.pattern), view))

    walk(get_resolver().url_patterns, "")
    return out


def _org_scoped() -> dict[str, type]:
    views: dict[str, type] = {}
    for path, view in _routes():
        if path.startswith(NOT_WORKSPACE):
            continue
        if ORG_IN_PATH.search(path) or view.__name__ in ORG_FROM_REQUEST:
            views.setdefault(view.__name__, view)
    return views


def test_the_walk_finds_the_org_views() -> None:
    found = _org_scoped()
    assert ORG_FROM_REQUEST <= set(found), ORG_FROM_REQUEST - set(found)
    # A sanity floor, so a regex that silently matches nothing cannot pass.
    assert {"LabMembersView", "DeptMembersView", "LabBillingView"} <= set(found)


def test_every_org_scoped_view_names_a_capability() -> None:
    missing: list[str] = []
    for name, view in sorted(_org_scoped().items()):
        declared = getattr(view, "capabilities", None)
        if not isinstance(declared, dict):
            missing.append(f"{name}: no capabilities declaration")
            continue
        served = {m.upper() for m in HTTP_METHODS if hasattr(view, m)}
        for method in sorted(served):
            capability = declared.get(method)
            if capability is None:
                missing.append(f"{name}.{method}: no capability")
            elif capability not in ALLOWED:
                missing.append(f"{name}.{method}: unknown {capability!r}")
        for method in sorted(set(declared) - served):
            missing.append(f"{name}.{method}: declared but not served")
    assert not missing, "\n".join(missing)


# -- The declarations are what the API enforces -----------------------------------


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


def _call(client: APIClient, method: str, path: str):
    if method == "GET":
        return client.get(path)
    return getattr(client, method.lower())(path, {}, format="json")


def _declared(path: str, method: str) -> str:
    view = resolve(path.split("?")[0]).func
    view_class = getattr(view, "view_class", None) or view.cls
    return view_class.capabilities[method]


@pytest.mark.django_db
def test_lab_routes_refuse_exactly_the_roles_without_the_capability() -> None:
    owner = _user("owner")
    lab = create_lab_workspace(owner, "Soil Lab").lab
    people = {"owner": owner}
    for role in ("admin", "member", "viewer"):
        people[role] = _user(role)
        LabMembership.objects.create(lab=lab, user=people[role], role=role)
    people["lead"] = _user("lead")
    LabMembership.objects.create(
        lab=lab, user=people["lead"], role="viewer", is_lead=True
    )
    people["stranger"] = _user("stranger")

    routes = [
        ("GET", f"/api/auth/labs/{lab.slug}/members/"),
        ("GET", f"/api/auth/labs/{lab.slug}/profile/"),
        ("PATCH", f"/api/auth/labs/{lab.slug}/profile/"),
        ("GET", f"/api/auth/labs/{lab.slug}/watch/"),
        ("GET", f"/api/auth/labs/{lab.slug}/invitations/"),
        ("GET", f"/api/auth/labs/{lab.slug}/invites/"),
        ("GET", f"/api/labs/{lab.slug}/billing/"),
        ("GET", f"/api/announcements/settings/?lab={lab.slug}"),
        ("PUT", f"/api/announcements/settings/?lab={lab.slug}"),
    ]
    client = APIClient()
    for who, user in people.items():
        client.force_authenticate(user)
        for method, path in routes:
            capability = _declared(path, method)
            allowed = caps.has_capability(user, lab, capability)
            code = _call(client, method, path).status_code
            assert (code == 403) != allowed, (who, method, path, code)


@pytest.mark.django_db
def test_department_routes_refuse_exactly_the_roles_without_the_capability() -> None:
    head = _user("head")
    department = create_department_workspace(head, "Earth Sciences").department
    people = {"head": head}
    for role in ("admin", "member", "viewer"):
        people[role] = _user(role)
        DeptMembership.objects.create(
            department=department, user=people[role], role=role
        )
    lab_pi = _user("lab_pi")
    lab = create_lab_workspace(lab_pi, "Rock Lab").lab
    lab.department = department
    lab.save(update_fields=["department"])
    people["affiliate"] = lab_pi
    people["stranger"] = _user("stranger")

    base = f"/api/auth/departments/{department.id}"
    routes = [
        ("GET", f"{base}/members/"),
        ("GET", f"{base}/labs/"),
        ("GET", f"{base}/profile/"),
        ("PATCH", f"{base}/profile/"),
        ("GET", f"{base}/invites/"),
        ("GET", f"/api/departments/{department.id}/billing/"),
        ("GET", f"/api/announcements/settings/?department={department.id}"),
        ("PUT", f"/api/announcements/settings/?department={department.id}"),
    ]
    client = APIClient()
    for who, user in people.items():
        client.force_authenticate(user)
        for method, path in routes:
            capability = _declared(path, method)
            allowed = caps.has_capability(user, department, capability)
            code = _call(client, method, path).status_code
            assert (code == 403) != allowed, (who, method, path, code)
