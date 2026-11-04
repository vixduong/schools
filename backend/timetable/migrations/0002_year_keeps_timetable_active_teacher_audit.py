from django.db import migrations

# A School year cannot shrink past its timetable entries (as with enrollments, schools.0003).
YEAR_UP = """
CREATE FUNCTION school_year_keeps_its_timetable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM timetable_timetableentry e
              WHERE e.school_year_id = NEW.id AND e.school_id = NEW.school_id
                AND (e.valid_from < NEW.starts_on OR e.valid_from > NEW.ends_on
                     OR e.valid_to > NEW.ends_on)) THEN
    RAISE EXCEPTION 'school year would leave a timetable entry outside it' USING ERRCODE = '23514',
      CONSTRAINT = 'school_year_keeps_its_timetable';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER school_year_keeps_its_timetable BEFORE UPDATE OF starts_on, ends_on
  ON schools_schoolyear
  FOR EACH ROW EXECUTE FUNCTION school_year_keeps_its_timetable();
"""
YEAR_DOWN = """
DROP TRIGGER school_year_keeps_its_timetable ON schools_schoolyear;
DROP FUNCTION school_year_keeps_its_timetable();
"""


def teacher_teaches(active_membership):
    """`timetableentry_teacher_teaches`; from here on the teacher's Membership must be active too."""
    join = (
        "JOIN accounts_membership m ON m.school_id = ra.school_id AND m.id = ra.membership_id"
        if active_membership
        else ""
    )
    active = "AND m.status = 'active'" if active_membership else ""
    locks = "OF ra, m" if active_membership else "OF ra"
    return f"""
CREATE OR REPLACE FUNCTION timetableentry_teacher_teaches() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM accounts_roleassignment ra {join}
    WHERE ra.school_id = NEW.school_id AND ra.membership_id = NEW.teacher_id {active}
      AND ra.role = 'subject_teacher' AND ra.status = 'active'
      AND ra.subject_id = NEW.subject_id AND ra.school_class_id = NEW.school_class_id
      AND ra.valid_from <= NEW.valid_from
      AND (ra.valid_to IS NULL OR ra.valid_to >= NEW.valid_from)
    FOR SHARE {locks};
  IF NOT FOUND THEN
    RAISE EXCEPTION 'the teacher does not teach this subject in this class' USING ERRCODE = '23514',
      CONSTRAINT = 'timetableentry_teacher_teaches';
  END IF;
  RETURN NEW;
END $$;
"""


# The replace deletes entries that never started: the log keeps them.
AUDIT_UP = (
    "CREATE TRIGGER audit_row_change AFTER INSERT OR UPDATE OR DELETE ON timetable_timetableentry "
    "FOR EACH ROW EXECUTE FUNCTION audit_row_change()"
)
AUDIT_DOWN = "DROP TRIGGER audit_row_change ON timetable_timetableentry"


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_harden"),
        ("timetable", "0001_bell_periods_and_timetable_entries"),
    ]

    operations = [
        migrations.RunSQL(YEAR_UP, YEAR_DOWN),
        migrations.RunSQL(teacher_teaches(True), teacher_teaches(False)),
        migrations.RunSQL(AUDIT_UP, AUDIT_DOWN),
    ]
