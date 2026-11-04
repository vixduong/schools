"""The audit log (read by the School admin) never stores personal free text it was not meant to."""

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

# Free-text columns an audit trigger may keep, each with the reason it is safe to.
ALLOWED = {
    # Entered by the School admin themself when recording a leave or transfer.
    ("schools_studentstatusevent", "reason"),
    # The School's own reason for granting the operator access, read by its admin by design.
    ("audit_supportgrant", "reason"),
}
FREE_TEXT = r"^(reason|note|.*comment)$"  # reason_started & co. are choice codes


def test_every_audited_table_hides_its_free_text():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, t.tgargs
              FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
             WHERE t.tgfoid = 'audit_row_change'::regproc AND NOT t.tgisinternal
            """
        )
        triggers = {table: bytes(args).decode().split("\x00") for table, args in cursor.fetchall()}
        cursor.execute(
            """
            SELECT table_name, column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = ANY(%s)
               AND (data_type = 'text' OR column_name ~ %s)
               AND data_type IN ('text', 'character varying')
            """,
            [list(triggers), FREE_TEXT],
        )
        exposed = sorted(
            (table, column)
            for table, column in cursor.fetchall()
            if column not in triggers[table] and (table, column) not in ALLOWED
        )
    assert triggers, "no audit triggers found"
    assert exposed == [], "pass these as hidden columns to audit_row_change(...) or allow them"
