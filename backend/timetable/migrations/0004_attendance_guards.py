from django.db import migrations

# An entry that has marks cannot lose them: ending it before a mark's date, or deleting it, is
# refused (SQLSTATE 23514, reported like a constraint). The API never does either (a replacement
# starts after today and marks are never later than today), so this is the net under a bug or a
# hand-written statement.
ENTRY_UP = """
CREATE FUNCTION timetableentry_keeps_its_attendance() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM timetable_attendancemark m
              WHERE m.school_id = OLD.school_id AND m.entry_id = OLD.id
                AND (TG_OP = 'DELETE' OR m."on" > NEW.valid_to)) THEN
    RAISE EXCEPTION 'the timetable entry has attendance marks the change would strand'
      USING ERRCODE = '23514', CONSTRAINT = 'timetableentry_keeps_its_attendance';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER timetableentry_keeps_its_attendance BEFORE UPDATE OF valid_to OR DELETE
  ON timetable_timetableentry
  FOR EACH ROW EXECUTE FUNCTION timetableentry_keeps_its_attendance();
"""
ENTRY_DOWN = """
DROP TRIGGER timetableentry_keeps_its_attendance ON timetable_timetableentry;
DROP FUNCTION timetableentry_keeps_its_attendance();
"""

# A period is taken on its day or after, never before: "today" is the School's, as in the audit
# trigger (timetable.0003). It also keeps every mark out of what a replacement deletes or ends.
FUTURE_UP = """
CREATE FUNCTION attendancemark_not_in_the_future() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW."on" > (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date THEN
    RAISE EXCEPTION 'attendance cannot be marked for a day that has not come'
      USING ERRCODE = '23514', CONSTRAINT = 'attendancemark_not_in_the_future';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER attendancemark_not_in_the_future BEFORE INSERT OR UPDATE OF "on"
  ON timetable_attendancemark
  FOR EACH ROW EXECUTE FUNCTION attendancemark_not_in_the_future();
"""
FUTURE_DOWN = """
DROP TRIGGER attendancemark_not_in_the_future ON timetable_attendancemark;
DROP FUNCTION attendancemark_not_in_the_future();
"""


class Migration(migrations.Migration):

    dependencies = [("timetable", "0003_attendance_marks")]

    operations = [
        migrations.RunSQL(ENTRY_UP, ENTRY_DOWN),
        migrations.RunSQL(FUTURE_UP, FUTURE_DOWN),
    ]
