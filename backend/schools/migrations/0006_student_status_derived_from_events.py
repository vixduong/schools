from django.db import migrations

# A student's status is now derived from the StudentStatusEvents as of a date, so a leave can be
# scheduled in advance without changing today's status. The events stay the source: no history is
# lost, only the stored copy and the triggers that kept it in sync go.
DROP_SYNC = """
DROP TRIGGER status_event_sets_student_status ON schools_studentstatusevent;
DROP FUNCTION status_event_sets_student_status();
DROP TRIGGER student_status_follows_events ON schools_student;
DROP FUNCTION student_status_follows_events();
"""

# Reverse: bring the stored copy back (per School, as RLS shows nothing otherwise) set to each
# student's latest event, then the triggers of schools.0003.
RESTORE_SYNC = """
DO $$
DECLARE sid bigint;
BEGIN
  FOR sid IN SELECT id FROM tenancy_school LOOP
    PERFORM set_config('app.school_id', sid::text, true);
    UPDATE schools_student s SET status = latest.status
      FROM (SELECT DISTINCT ON (e.student_id) e.student_id, e.status
              FROM schools_studentstatusevent e
             ORDER BY e.student_id, e."on" DESC, e.id DESC) latest
     WHERE s.id = latest.student_id;
  END LOOP;
  PERFORM set_config('app.school_id', '', true);
END $$;

CREATE FUNCTION student_status_follows_events() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected text;
BEGIN
  SELECT e.status INTO expected FROM schools_studentstatusevent e
   WHERE e.school_id = NEW.school_id AND e.student_id = NEW.id
   ORDER BY e."on" DESC, e.id DESC LIMIT 1;
  IF NEW.status IS DISTINCT FROM COALESCE(expected, 'studying') THEN
    RAISE EXCEPTION 'student status changes only through a status event'
      USING ERRCODE = '23514', CONSTRAINT = 'student_status_follows_events';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER student_status_follows_events BEFORE INSERT OR UPDATE OF status ON schools_student
  FOR EACH ROW EXECUTE FUNCTION student_status_follows_events();

CREATE FUNCTION status_event_sets_student_status() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM schools_student s
   WHERE s.school_id = NEW.school_id AND s.id = NEW.student_id FOR UPDATE;
  UPDATE schools_student s SET status = (
      SELECT e.status FROM schools_studentstatusevent e
       WHERE e.school_id = NEW.school_id AND e.student_id = NEW.student_id
       ORDER BY e."on" DESC, e.id DESC LIMIT 1)
   WHERE s.school_id = NEW.school_id AND s.id = NEW.student_id;
  RETURN NULL;
END $$;
CREATE TRIGGER status_event_sets_student_status AFTER INSERT ON schools_studentstatusevent
  FOR EACH ROW EXECUTE FUNCTION status_event_sets_student_status();
"""


class Migration(migrations.Migration):
    dependencies = [("schools", "0005_national_id_digits_and_membership_lock")]

    operations = [
        migrations.RunSQL(DROP_SYNC, RESTORE_SYNC),
        migrations.RemoveField(model_name="student", name="status"),
    ]
