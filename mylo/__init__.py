"""Mylo — Mycelium's Discord presence.

Two consumers share this package:

- ``mylo.reporting`` — a dependency-free (stdlib only) seam the daily run
  (`manual_all.py`) calls to post errors and status to Mylo's Discord error
  channel over the REST API. It never raises and never blocks the run.
- ``mylo.bot`` — the persistent ``discord.py`` gateway process (its own systemd
  service) that owns slash commands and Mylo's channel presence.

Both read ``.env-mylo`` at the repository root via :mod:`mylo.config`.
"""
