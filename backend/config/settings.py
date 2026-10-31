import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"

# Schools live at <subdomain>.<BASE_DOMAIN>. TenantMiddleware is the host gate (404 for any
# host that is not a known School), so Django's own host check is left open.
BASE_DOMAIN = os.environ["BASE_DOMAIN"].lower()
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "rest_framework",
    "drf_spectacular",
    "tenancy",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "tenancy.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Two roles (ADR 0001): "owner" runs migrations, "app" serves requests and cannot bypass RLS.
# DB_ROLE picks which credentials this process uses; requests must run as "app".
APP_DB_USER = os.environ["DB_APP_USER"]
APP_DB_PASSWORD = os.environ["DB_APP_PASSWORD"]
OWNER_DB_USER = os.environ["DB_OWNER_USER"]
OWNER_DB_PASSWORD = os.environ["DB_OWNER_PASSWORD"]
_owner = os.environ.get("DB_ROLE", "app") == "owner"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ["DB_PORT"],
        "USER": OWNER_DB_USER if _owner else APP_DB_USER,
        "PASSWORD": OWNER_DB_PASSWORD if _owner else APP_DB_PASSWORD,
        # TenantMiddleware owns the outer transaction and sets the School GUC there.
        # ATOMIC_REQUESTS adds a savepoint around the view: an exception, or DRF's
        # set_rollback() on an error response, undoes the view's writes while the GUC survives.
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# No Account/session yet (slice 3), so the API is open; tenancy is enforced by RLS regardless.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "School Platform API",
    "VERSION": "0.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

USE_TZ = True
TIME_ZONE = "Asia/Ho_Chi_Minh"
