from django.db import migrations

# A mark's note is personal free text ("ốm", "đi viện"): the audit log, which the School admin
# reads, keeps who corrected which mark and its status, not the note (as with leave reasons, 0006).
WHEN = "FOR EACH ROW WHEN (OLD.\"on\" < (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) "


def trigger(hidden):
    return (
        "DROP TRIGGER audit_row_change ON timetable_attendancemark; "
        "CREATE TRIGGER audit_row_change AFTER UPDATE ON timetable_attendancemark "
        f"{WHEN}EXECUTE FUNCTION audit_row_change({hidden})"
    )


class Migration(migrations.Migration):
    dependencies = [("timetable", "0006_leave_request_send_guard_and_audit_privacy")]

    operations = [migrations.RunSQL(trigger("'note'"), trigger(""))]
