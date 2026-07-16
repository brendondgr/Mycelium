"""Discord integration services.

``resolve`` is the single ORM boundary: it is the only module in the Discord path
that imports a model. Everything else here (oauth, probe, activation, reconcile,
state, errors, audit, discord_api) orchestrates REST calls, Redis, and audit
logging, and reaches the database only through ``resolve``. This is asserted by a
test (``test_discord_path_imports_no_models_outside_resolve_module``).
"""
