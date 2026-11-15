"""Refuse to run without the backend's suite plugin.

``config.pytest_plugin`` pins billing, sign-up and tool settings for every test
and is loaded by ``addopts`` in ``web/backend/pyproject.toml``. When one run
names both ``web/backend`` and ``../../tools`` paths (or only tools paths),
pytest takes the repository root's ``pyproject.toml`` as its config instead,
the plugin never loads, and plan and billing tests fail for no reason of their
own. This makes that a clear error instead.
"""

import pytest


def pytest_configure(config):
    if not config.pluginmanager.has_plugin("config.pytest_plugin"):
        raise pytest.UsageError(
            f"pytest read {config.inipath} instead of web/backend/pyproject.toml, "
            "so the suite plugin (config.pytest_plugin) is not loaded. Run from "
            "web/backend with `-c pyproject.toml` when naming paths, or `make test`."
        )
