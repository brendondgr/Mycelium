"""The model servers this instance may use, and which one each component uses.

The host declares servers in ``mycelium.toml`` (``[llm.providers.<name>]``) and
routes components to them (``[llm.routes]``); ``config/instance.py`` resolves
both and ``settings.py`` publishes them as ``LLM_SERVERS`` / ``LLM_ROUTES``. A
server named ``local`` always exists: unless the host declares it, it is the
endpoint in ``.env`` (``LLM_BASE_URL``, ``LLM_MODEL``), read live from settings
so nothing changes for an install that declares nothing.

This module answers three questions and never raises doing so:

* :func:`resolve` — which server and model a component's calls go to;
* :func:`options` — what each server reports (models, context windows) and
  whether it answers, cached by ``llmkit.ModelCache`` (300 s, 15 s after an
  error);
* :func:`context_window` — how much a server's model can hold.

Keys are read from the environment only when a client is built
(:func:`api_key`); nothing here returns, logs or caches one.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

LOCAL = "local"
#: Discovery is cached this long, and this long after an error.
CACHE_TTL = 300.0
ERROR_TTL = 15.0


@dataclass(frozen=True)
class Route:
    """Where one component's calls go. ``problem`` says why a route was not
    honoured (the server is unknown, disabled, or cloud while cloud is off)."""

    component: str
    server: str
    kind: str
    model: str
    label: str
    location: str
    base_url: str
    requested: str = ""
    problem: str = ""

    def public(self) -> dict[str, str]:
        """The ``{name, label, location}`` a surface shows (shared contract S3)."""
        return {"name": self.model, "label": self.label, "location": self.location,
                "server": self.server}


# --------------------------------------------------------------------------- #
# The table
# --------------------------------------------------------------------------- #


def table():
    """The resolved :class:`config.instance.LLMServers`, from live settings."""
    from django.conf import settings

    from config.instance import LLMServers, derive_location

    servers = {name: dict(s) for name, s in
               (getattr(settings, "LLM_SERVERS", None) or {}).items()}
    local = servers.get(LOCAL)
    if local is None or local.get("synthesized"):
        local = {**_synthesized_defaults(), **(local or {})}
        # The .env endpoint is read live, so a test's override_settings or a
        # changed .env behaves exactly as it did before servers existed.
        local.update(
            base_url=str(getattr(settings, "LLM_BASE_URL", "") or ""),
            model=str(getattr(settings, "LLM_MODEL", "") or ""),
            timeout=float(getattr(settings, "LLM_TIMEOUT", 60.0)),
            connect_timeout=float(getattr(settings, "LLM_CONNECT_TIMEOUT", 5.0)),
        )
        if not local.get("location_stated"):
            local["location"] = derive_location(local["kind"], local["base_url"])
        servers[LOCAL] = local
    return LLMServers(
        servers=servers,
        routes=dict(getattr(settings, "LLM_ROUTES", None) or {}),
        default=str(getattr(settings, "LLM_DEFAULT_SERVER", "") or LOCAL),
        allow_cloud=bool(getattr(settings, "LLM_ALLOW_CLOUD", False)),
        fallback=list(getattr(settings, "LLM_FALLBACK", None) or []),
    )


def _synthesized_defaults() -> dict[str, Any]:
    return {
        "name": LOCAL, "kind": "openai_compatible", "api_key_env": "LLM_API_KEY",
        "label": "Local model", "enabled": True, "location": "local",
        "location_stated": False, "context_window": 0, "reasoning": "",
        "model_allow": [], "model_deny": [], "synthesized": True,
    }


def server(name: str) -> dict[str, Any] | None:
    """One server's resolved fields (no key), or ``None``."""
    return table().servers.get(name)


def api_key(entry: dict[str, Any]) -> str:
    """The key for a server, read from the environment at the moment of use."""
    if entry.get("synthesized"):
        from django.conf import settings

        return str(getattr(settings, "LLM_API_KEY", "") or "")
    name = entry.get("api_key_env") or ""
    return os.environ.get(name, "") if name else ""


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


def _route_text(component: str, routes: dict[str, str]) -> str:
    """A component's route: exact, else its nearest dotted parent
    (``intake`` covers ``intake.clusters``)."""
    name = component
    while name:
        if name in routes:
            return routes[name]
        name = name.rpartition(".")[0]
    return ""


def resolve(component: str = "") -> Route:
    """The server and model ``component``'s calls go to. Never raises.

    A route to a server that may not be called (unknown, disabled, cloud while
    ``llm.allow_cloud`` is false) falls back to ``llm.default`` and then to
    ``local``, and says so in ``problem``. It never falls through to a cloud
    server the host did not choose.
    """
    t = table()
    requested = _route_text(component, t.routes) or t.default or LOCAL
    name, _, model = requested.partition(":")
    problem = ""
    if not t.callable(name):
        problem = _why_not(t, name)
        model = ""
        name = t.default if t.callable(t.default) else LOCAL
        if name == LOCAL and not t.callable(LOCAL):
            problem = problem or _why_not(t, LOCAL)
        logger.warning("llm route %r for %r not honoured (%s); using %r",
                       requested, component or "unlabelled", problem, name)
    entry = t.servers[name] if name in t.servers else t.servers[LOCAL]
    return Route(
        component=component,
        server=entry["name"],
        kind=entry["kind"],
        model=model or entry["model"],
        label=entry["label"],
        location=entry["location"],
        base_url=entry["base_url"],
        requested=requested,
        problem=problem,
    )


def _why_not(t, name: str) -> str:
    entry = t.servers.get(name)
    if entry is None:
        return f"no server named {name!r}"
    if not entry["enabled"]:
        return f"{name!r} is disabled"
    return f"{name!r} is a cloud server and llm.allow_cloud is false"


def routes() -> dict[str, dict[str, Any]]:
    """Every explicitly routed component plus ``*`` (everything else)."""
    t = table()
    out = {"*": _route_row(resolve(""))}
    for component in sorted(t.routes):
        out[component] = _route_row(resolve(component))
    return out


def _route_row(route: Route) -> dict[str, Any]:
    return {"server": route.server, "model": route.model, "label": route.label,
            "location": route.location, "requested": route.requested,
            "problem": route.problem or None}


# --------------------------------------------------------------------------- #
# llmkit registry, discovery and health
# --------------------------------------------------------------------------- #

_lock = threading.RLock()
_registry: Any = None
_signature = ""


def provider_config(entry: dict[str, Any]):
    """The ``llmkit.ProviderConfig`` for one server (key read from the env)."""
    from apps.core.llmkit import build_config

    base_url = entry.get("base_url") or None
    config = build_config(
        entry["name"],
        entry["kind"],
        base_url=base_url,
        default_model=entry.get("model") or None,
        label=entry.get("label"),
        timeout=float(entry.get("timeout") or 60.0),
        connect_timeout=float(entry.get("connect_timeout") or 5.0),
        # Retrying a dead server only delays the caller's own fallback.
        max_retries=0,
        model_allow=list(entry.get("model_allow") or []),
        model_deny=list(entry.get("model_deny") or []),
        discovery_ttl=CACHE_TTL,
        enabled=bool(entry.get("enabled", True)),
    )
    # The key comes from the variable the host named, never from the kind's
    # default variable (build_config would otherwise read ANTHROPIC_API_KEY
    # for a server whose key the host keeps under another name).
    config.api_key = api_key(entry) or None
    config.api_key_env = None
    return config


def _table_signature(t) -> str:
    keyed = {n: {**s, "_key": hashlib.sha256(api_key(s).encode()).hexdigest()}
             for n, s in t.servers.items()}
    return hashlib.sha256(json.dumps(keyed, sort_keys=True, default=str)
                          .encode()).hexdigest()


def registry():
    """The process's ``llmkit.Registry`` over every server that may be called.

    Rebuilt when the server table changes (a test's ``override_settings``),
    so its discovery cache never answers for a server that is not there.
    """
    global _registry, _signature
    from apps.core.llmkit import ModelCache, Registry

    t = table()
    signature = _table_signature(t)
    with _lock:
        if _registry is None or signature != _signature:
            configs = []
            for name, entry in t.servers.items():
                if not t.callable(name):
                    continue
                try:
                    configs.append(provider_config(entry))
                except Exception as exc:  # noqa: BLE001 - reported by options()
                    logger.warning("llm server %r not loadable: %s", name, exc)
            reg = Registry(configs, cache_ttl=CACHE_TTL)
            reg.cache = ModelCache(ttl=CACHE_TTL, error_ttl=ERROR_TTL)
            _registry, _signature = reg, signature
        return _registry


def reset() -> None:
    """Forget the registry and its cache (tests; a config reload)."""
    global _registry, _signature
    with _lock:
        _registry, _signature = None, ""


def _model_row(m) -> dict[str, Any]:
    return {
        "id": m.id,
        "label": m.label(),
        "context_window": m.context_window,
        "capabilities": sorted(c.value for c in m.capabilities),
        "loaded": m.meta.get("loaded"),
    }


def options(*, force: bool = False) -> list[dict[str, Any]]:
    """Per server, what it reports and whether it answers. Never raises.

    ``{server, label, kind, location, enabled, callable, ok, error, cached,
    default, model, models: [{id, label, context_window, capabilities,
    loaded}]}``. An unreachable server is a normal state: ``ok: false`` with
    the reason. Every reachable server is asked at once, so a dead one costs
    its own connect timeout and does not slow the others.
    """
    t = table()
    try:
        reg = registry()
        names = [n for n in t.servers if n in reg]
        timeout = max([float(t.servers[n].get("connect_timeout") or 5.0)
                       for n in names] or [5.0]) + 10.0
        results = reg.discover_all(force=force, timeout=timeout) if names else {}
    except Exception as exc:  # noqa: BLE001 - discovery never breaks a caller
        logger.warning("llm discovery failed: %s", exc)
        reg, results = None, {}
    rows = []
    for name, entry in t.servers.items():
        row = {
            "server": name,
            "label": entry["label"],
            "kind": entry["kind"],
            "location": entry["location"],
            "enabled": entry["enabled"],
            "callable": t.callable(name),
            "default": name == t.default,
            "model": entry["model"],
            "ok": False,
            "error": None,
            "cached": False,
            "models": [],
        }
        result = results.get(name)
        if not entry["enabled"]:
            row["error"] = "disabled"
        elif not t.callable(name):
            row["error"] = "cloud servers are off (llm.allow_cloud = false)"
        elif result is None:
            row["error"] = "not loadable; see `ops/mycelium config validate`"
        else:
            row["ok"] = result.ok
            row["error"] = result.error
            row["cached"] = result.cached
            row["models"] = [_model_row(m) for m in result.models]
        rows.append(row)
    return rows


def health(name: str, *, force: bool = False) -> tuple[bool, str | None]:
    """``(answers, reason)`` for one server, from discovery. Never raises."""
    t = table()
    if name not in t.servers:
        return False, f"no server named {name!r}"
    if not t.callable(name):
        return False, _why_not(t, name)
    try:
        reg = registry()
        if name not in reg:
            return False, "not loadable"
        result = reg.discover(name, force=force)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    return result.ok, result.error


#: Used when neither the host nor the server says how much a model holds.
DEFAULT_CONTEXT_WINDOW = 32768


def context_window(name: str, model: str = "") -> int:
    """Tokens ``model`` on server ``name`` can hold.

    The server's stated ``context_window`` wins; otherwise what discovery
    reports (vLLM ``max_model_len``, llama.cpp ``/props``, Ollama
    ``/api/show``, Anthropic and Gemini limits); otherwise 32768.
    """
    entry = server(name) or {}
    stated = int(entry.get("context_window") or 0)
    if stated > 0:
        return stated
    model = model or entry.get("model") or ""
    try:
        reg = registry()
        if name in reg:
            for m in reg.discover(name).models:
                if m.id == model and m.context_window:
                    return int(m.context_window)
    except Exception:  # noqa: BLE001 - a guess is better than a failed turn
        logger.debug("context window discovery failed for %r", name,
                     exc_info=True)
    return DEFAULT_CONTEXT_WINDOW


def warm() -> None:
    """Fill the discovery cache in the background (worker and web start)."""

    def run() -> None:
        try:
            options()
        except Exception:  # noqa: BLE001
            logger.debug("llm discovery warm-up failed", exc_info=True)

    threading.Thread(target=run, name="llm-servers-warm", daemon=True).start()
