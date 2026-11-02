from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created

# A request left idle inside its transaction (a stuck worker) releases its locks after this.
IDLE_IN_TRANSACTION_TIMEOUT = "30s"


def guard_app_role(sender, connection, **kwargs):
    """Every new connection as the app role: refuse a role that bypasses RLS (a superuser or
    BYPASSRLS would make every tenant policy a no-op), and bound idle transactions."""
    if connection.settings_dict["USER"] != settings.APP_DB_USER:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper OR rolbypassrls, set_config("
            "'idle_in_transaction_session_timeout', %s, false)"
            " FROM pg_roles WHERE rolname = current_user",
            [IDLE_IN_TRANSACTION_TIMEOUT],
        )
        (bypasses, _) = cursor.fetchone()
    if bypasses:
        connection.close()
        raise ImproperlyConfigured(
            f"The app role {settings.APP_DB_USER} bypasses RLS (superuser or BYPASSRLS): refusing."
        )


class TenancyConfig(AppConfig):
    name = "tenancy"

    def ready(self):
        connection_created.connect(guard_app_role, dispatch_uid="tenancy.guard_app_role")
