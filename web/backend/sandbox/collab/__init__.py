"""The collaboration-network sandbox: a synthetic world, the real pipeline.

Run from ``web/backend``::

    uv run --project . python -m sandbox.collab all --people 120

It points itself at the ``mycelium_sandbox`` database before Django starts and
refuses to run anywhere else (:mod:`.bootstrap`).
"""
