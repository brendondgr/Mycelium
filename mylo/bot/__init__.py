"""Mylo's persistent Discord gateway bot (``python -m mylo.bot``).

A single always-on ``discord.py`` process that owns Mylo's slash commands and
channel presence. Error/status *delivery* from the daily run does not depend on
this process being up — that goes through :mod:`mylo.reporting` over REST — so
the bot is free to be a convenience surface (health, last-run status) rather than
a critical path.
"""
