"""How loaded tools are spliced into the platform: URLs, settings, events."""

from __future__ import annotations

from types import SimpleNamespace

from django.urls import include, path

from tools._framework import events, host


def test_splice_urls_inserts_after_the_named_include():
    platform = [
        path("a/", include("tools._framework.urls")),
        path("api/", include("apps.research.urls")),
        path("api/", include("apps.core.urls")),
    ]
    out = host.splice_urls(
        platform,
        [
            ("api/", "tools._framework.urls", "apps.research.urls"),
        ],
    )
    names = [getattr(getattr(p, "urlconf_name", None), "__name__", None) for p in out]
    assert names == [
        "tools._framework.urls",
        "apps.research.urls",
        "tools._framework.urls",
        "apps.core.urls",
    ]


def test_events_reach_subscribers_and_isolate_failures():
    seen = []

    def good(**payload):
        seen.append(payload)

    def bad(**payload):
        raise RuntimeError("boom")

    events.subscribe("t.evt", bad)
    events.subscribe("t.evt", good)
    try:
        assert events.publish("t.evt", ids=[1]) == 1
        assert seen == [{"ids": [1]}]
    finally:
        events.unsubscribe("t.evt", bad)
        events.unsubscribe("t.evt", good)


def test_framework_is_installed_and_reports(settings, client, django_user_model):
    assert host.FRAMEWORK_APP in settings.INSTALLED_APPS
    user = django_user_model.objects.create_user(
        username="tools-status", password="pass-123"
    )
    client.force_login(user)
    response = client.get("/api/tools/")
    assert response.status_code == 200
    names = [row["name"] for row in response.json()["tools"]]
    assert names == settings.TOOLS_REPORT.order
    assert all("reason" not in row for row in response.json()["tools"])


def test_publish_settings_only_for_loaded_tools(monkeypatch):
    class Report(SimpleNamespace):
        def loaded(self):
            return []

    ns: dict = {}
    host.publish_settings(
        ns,
        Report(tools={}, tools_dir="/nonexistent", order=[]),
        SimpleNamespace(tools={}),
    )
    assert ns == {}


def test_every_loaded_tool_has_its_declared_app_label(settings):
    """Django must pick the tool's own AppConfig (and so its label), not fall
    back to a default config named after the package."""
    from django.apps import apps

    for name in settings.TOOLS_REPORT.loaded():
        item = settings.TOOLS_REPORT.tools[name]
        config = apps.get_app_config(item.label)
        assert config.name == item.package
