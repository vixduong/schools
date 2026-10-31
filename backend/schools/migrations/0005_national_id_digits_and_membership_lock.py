from django.db import migrations, models

# enrollment_fits_student_membership used to lock the student row only when it had a Membership,
# so a concurrent "give this student a Membership" did not wait for an enrollment being inserted
# (and vice versa). Now the student row is always read FOR SHARE, then the rule is applied.
LOCK_UP = """
CREATE OR REPLACE FUNCTION enrollment_fits_student_membership() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE m bigint;
BEGIN
  SELECT s.membership_id INTO m FROM schools_student s
   WHERE s.school_id = NEW.school_id AND s.id = NEW.student_id FOR SHARE;
  IF m IS NOT NULL THEN
    PERFORM 1 FROM schools_schoolclass c
      JOIN schools_grade g ON g.school_id = c.school_id AND g.id = c.grade_id
      JOIN schools_level l ON l.school_id = g.school_id AND l.id = g.level_id
     WHERE c.school_id = NEW.school_id AND c.id = NEW.school_class_id
       AND l.kind IN ('lower_secondary', 'upper_secondary');
    IF NOT FOUND THEN
      RAISE EXCEPTION 'a student with a membership enrolls only in Lower or Upper Secondary'
        USING ERRCODE = '23514', CONSTRAINT = 'enrollment_fits_student_membership';
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""

LOCK_DOWN = """
CREATE OR REPLACE FUNCTION enrollment_fits_student_membership() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM schools_student s
   WHERE s.school_id = NEW.school_id AND s.id = NEW.student_id AND s.membership_id IS NOT NULL
     FOR SHARE;
  IF FOUND THEN
    PERFORM 1 FROM schools_schoolclass c
      JOIN schools_grade g ON g.school_id = c.school_id AND g.id = c.grade_id
      JOIN schools_level l ON l.school_id = g.school_id AND l.id = g.level_id
     WHERE c.school_id = NEW.school_id AND c.id = NEW.school_class_id
       AND l.kind IN ('lower_secondary', 'upper_secondary');
    IF NOT FOUND THEN
      RAISE EXCEPTION 'a student with a membership enrolls only in Lower or Upper Secondary'
        USING ERRCODE = '23514', CONSTRAINT = 'enrollment_fits_student_membership';
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("schools", "0004_seed_secondary_assessment_profile")]

    operations = [
        migrations.AddConstraint(
            model_name="student",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("national_id__isnull", True),
                    ("national_id__regex", "^[0-9]{12}$"),
                    _connector="OR",
                ),
                name="student_national_id_is_12_digits",
            ),
        ),
        migrations.RunSQL(LOCK_UP, LOCK_DOWN),
    ]
