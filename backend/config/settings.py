import os
from pathlib import Path

from .cookies import parse_secure_cookies
from .env import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"

# Schools live at <subdomain>.<BASE_DOMAIN>. TenantMiddleware is the host gate (404 for any
# host that is not a known School), so Django's own host check is left open.
BASE_DOMAIN = os.environ["BASE_DOMAIN"].lower()
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    # Required by sessions/DRF. Its group and permission tables stay unused and ungranted.
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
    "tenancy",
    "accounts",
    "schools",
    "permissions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Tenant first: sessions are read and saved inside the School's transaction.
    "tenancy.middleware.TenantMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Right after it: Django's request.user must not outlive a School mismatch.
    "accounts.middleware.SchoolBoundUserMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

AUTH_USER_MODEL = "accounts.Account"
# Applied when activation creates an Account (the only place a password is chosen today).
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},  # 8
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# Cookies (ADR 0003). Host-only: no Domain, and the __Host- prefix makes browsers enforce it.
# The prefix needs Secure, so plain-http local dev sets SECURE_COOKIES=false (see .env.example);
# that is refused unless DJANGO_DEBUG=1.
SECURE_COOKIES = parse_secure_cookies(os.environ.get("SECURE_COOKIES"), DEBUG)
_cookie_prefix = "__Host-" if SECURE_COOKIES else ""
SESSION_COOKIE_NAME = f"{_cookie_prefix}sessionid"
CSRF_COOKIE_NAME = f"{_cookie_prefix}csrftoken"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "Lax"

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

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.SchoolSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["accounts.permissions.HasMembership"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "School Platform API",
    "VERSION": "0.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Several models share the field names `status` and `kind`; give each choice set one name.
    "ENUM_NAME_OVERRIDES": {
        "LevelKindEnum": "schools.models.Level.Kind",
        "StudentStatusEnum": "schools.models.Student.Status",
        "RoleAssignmentStatusEnum": "accounts.models.RoleAssignment.Status",
        "InvitationKindEnum": "accounts.models.Invitation.Kind",
        "ImportBatchKindEnum": "schools.models.ImportBatch.Kind",
    },
}

USE_TZ = True
TIME_ZONE = "Asia/Ho_Chi_Minh"
