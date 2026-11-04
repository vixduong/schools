from django.db import migrations

# A request is sent waiting, from today (the School's day, not the database session's UTC one),
# for a student enrolled that day inside the enrollment's school year. The API checks the same
# for its messages; this holds it for every other writer. Reported like a constraint (23514).
# The parent rows are locked FOR SHARE, as in timetable.0003.
SEND_UP = """
CREATE FUNCTION leaverequest_on_send() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status <> 'waiting'
     OR NEW.from_on < (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date THEN
    RAISE EXCEPTION 'a leave request is sent waiting and from today'
      USING ERRCODE = '23514', CONSTRAINT = 'leaverequest_on_send';
  END IF;
  PERFORM 1 FROM schools_enrollment en
    JOIN schools_schoolyear y ON y.school_id = en.school_id AND y.id = en.school_year_id
    WHERE en.school_id = NEW.school_id AND en.student_id = NEW.student_id
      AND en.valid_from <= NEW.from_on AND (en.valid_to IS NULL OR en.valid_to >= NEW.from_on)
      AND y.starts_on <= NEW.from_on AND NEW.from_on <= y.ends_on
    FOR SHARE OF en, y;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'the student is not enrolled on the first day'
      USING ERRCODE = '23514', CONSTRAINT = 'leaverequest_on_send';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER leaverequest_on_send BEFORE INSERT ON timetable_leaverequest
  FOR EACH ROW EXECUTE FUNCTION leaverequest_on_send();
"""
SEND_DOWN = """
DROP TRIGGER leaverequest_on_send ON timetable_leaverequest;
DROP FUNCTION leaverequest_on_send();
"""

# The audit log is read by the School admin, who has no business with why a child is away or
# what the teacher answered ("Least data", docs/roles.md): both texts stay out of `details`.
AUDIT_UP = """
DROP TRIGGER audit_row_change ON timetable_leaverequest;
CREATE TRIGGER audit_row_change AFTER INSERT OR UPDATE ON timetable_leaverequest
  FOR EACH ROW EXECUTE FUNCTION audit_row_change('reason', 'decision_comment');
"""
AUDIT_DOWN = """
DROP TRIGGER audit_row_change ON timetable_leaverequest;
CREATE TRIGGER audit_row_change AFTER INSERT OR UPDATE ON timetable_leaverequest
  FOR EACH ROW EXECUTE FUNCTION audit_row_change();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0005_leave_requests'),
    ]

    operations = [
        migrations.RunSQL(SEND_UP, SEND_DOWN),
        migrations.RunSQL(AUDIT_UP, AUDIT_DOWN),
    ]
