"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Ask each model server what it serves once, in the background, so the first
# lookup is cached (apps.core.llm_servers). Never delays or fails the start.
from apps.core import llm_servers  # noqa: E402

llm_servers.warm()
