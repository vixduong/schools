from .settings import *  # noqa: F403

# pytest-django creates and migrates the test database, which needs the owner role.
# Isolation tests switch to the app role explicitly (see tenancy/tests/conftest.py).
DATABASES["default"]["USER"] = OWNER_DB_USER  # noqa: F405
DATABASES["default"]["PASSWORD"] = OWNER_DB_PASSWORD  # noqa: F405
