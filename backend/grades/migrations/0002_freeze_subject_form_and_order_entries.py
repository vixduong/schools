from django.db import migrations

# A subject's form (scored or comment only) decides which columns a gradebook has and what its
# entries carry, so it is frozen once a gradebook of the subject exists (as
# `subjectload_frozen_by_gradebooks`, grades.0001). Opening a gradebook holds the subject FOR NO KEY
# UPDATE, so an opening and an edit of the form take turns. A Level's kind needs no such trigger:
# it never changes (`level_kind_is_fixed`, schools.0001).
FREEZE_UP = """
CREATE FUNCTION subject_assessment_frozen_by_gradebooks() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.assessment IS DISTINCT FROM OLD.assessment AND EXISTS (
       SELECT 1 FROM grades_gradebook g
        WHERE g.school_id = NEW.school_id AND g.subject_id = NEW.id) THEN
    RAISE EXCEPTION 'a gradebook already uses this subject' USING ERRCODE = '23514',
      CONSTRAINT = 'subject_assessment_frozen_by_gradebooks';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER subject_assessment_frozen_by_gradebooks BEFORE UPDATE OF assessment
  ON schools_subject
  FOR EACH ROW EXECUTE FUNCTION subject_assessment_frozen_by_gradebooks();
"""
FREEZE_DOWN = """
DROP TRIGGER subject_assessment_frozen_by_gradebooks ON schools_subject;
DROP FUNCTION subject_assessment_frozen_by_gradebooks();
"""

# The latest entry of a cell is its score (by time, then id), so an entry is never dated before
# one the cell already has. The API takes its time from the database clock after locking the
# gradebook; this keeps the rule true for any other writer. Only a writer holding the gradebook
# lock (as every save does) is ordered against a concurrent one.
ORDER_UP = """
CREATE FUNCTION scoreentry_in_order() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM grades_scoreentry e
              WHERE e.school_id = NEW.school_id AND e.column_id = NEW.column_id
                AND e.student_id = NEW.student_id AND e.entered_at > NEW.entered_at) THEN
    RAISE EXCEPTION 'an entry is not dated before the cell''s latest one' USING ERRCODE = '23514',
      CONSTRAINT = 'scoreentry_in_order';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER scoreentry_in_order BEFORE INSERT ON grades_scoreentry
  FOR EACH ROW EXECUTE FUNCTION scoreentry_in_order();
"""
ORDER_DOWN = """
DROP TRIGGER scoreentry_in_order ON grades_scoreentry;
DROP FUNCTION scoreentry_in_order();
"""


class Migration(migrations.Migration):
    dependencies = [("grades", "0001_gradebook_entry")]

    operations = [
        migrations.RunSQL(FREEZE_UP, FREEZE_DOWN),
        migrations.RunSQL(ORDER_UP, ORDER_DOWN),
    ]
