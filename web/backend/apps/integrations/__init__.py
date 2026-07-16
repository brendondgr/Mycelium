"""Third-party integrations.

Currently: Discord identity + lab linking (apps.integrations.services). Mylo owns
no data — every Discord-originated database touch goes through
``apps.integrations.services.resolve``, the single ORM boundary for this app.
"""
