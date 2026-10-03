"""Fail-closed WSGI entry point for the Render-only service."""

import os

from django.core.wsgi import get_wsgi_application


os.environ["DJANGO_SETTINGS_MODULE"] = "dcd_project.settings_render"
application = get_wsgi_application()
