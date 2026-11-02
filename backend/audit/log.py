import json

from django.db import connection


def record(action: str, target=None, details: dict | None = None) -> None:
    """Log an event that is no row write (a sensitive read, a support command) in the current
    School's audit log, as the transaction's actor (`tenancy.rls.set_actor`)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT audit_record(%s, %s, %s, %s::jsonb)",
            [
                action,
                target._meta.db_table if target is not None else None,
                target.pk if target is not None else None,
                json.dumps(details or {}, default=str),
            ],
        )
