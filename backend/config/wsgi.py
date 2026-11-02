import os

from django.core.wsgi import get_wsgi_application

from config.observability import setup_tracing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
setup_tracing()  # before the app loads, so every request is traced
application = get_wsgi_application()
