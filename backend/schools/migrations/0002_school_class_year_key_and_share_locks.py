from django.db import migrations, models

# Cross-table triggers read a parent row and decide from it. Without a lock, a concurrent
# transaction could change that parent between the read and the commit and slip a bad row in, so
# the parent is read FOR SHARE (a concurrent UPDATE of it waits). PERFORM ... FOR SHARE replaces
# the EXISTS form because a row lock is not allowed inside that subquery.
SHARE_UP = """
CREATE OR REPLACE FUNCTION term_inside_school_year() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM schools_schoolyear y
    WHERE y.id = NEW.school_year_id AND y.school_id = NEW.school_id
      AND y.starts_on <= NEW.starts_on AND NEW.ends_on <= y.ends_on
    FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'term must lie inside its school year' USING ERRCODE = '23514',
      CONSTRAINT = 'term_inside_school_year';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION grade_number_fits_level() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM schools_level l
    WHERE l.id = NEW.level_id AND l.school_id = NEW.school_id
      AND CASE l.kind WHEN 'primary' THEN NEW.number BETWEEN 1 AND 5
                      WHEN 'lower_secondary' THEN NEW.number BETWEEN 6 AND 9
                      WHEN 'upper_secondary' THEN NEW.number BETWEEN 10 AND 12
                      ELSE false END
    FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'grade number does not fit its level' USING ERRCODE = '23514',
      CONSTRAINT = 'grade_number_fits_level';
  END IF;
  RETURN NEW;
END $$;
"""

SHARE_DOWN = """
CREATE OR REPLACE FUNCTION term_inside_school_year() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM schools_schoolyear y
                  WHERE y.id = NEW.school_year_id AND y.school_id = NEW.school_id
                    AND y.starts_on <= NEW.starts_on AND NEW.ends_on <= y.ends_on) THEN
    RAISE EXCEPTION 'term must lie inside its school year' USING ERRCODE = '23514',
      CONSTRAINT = 'term_inside_school_year';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION grade_number_fits_level() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM schools_level l
                  WHERE l.id = NEW.level_id AND l.school_id = NEW.school_id
                    AND CASE l.kind WHEN 'primary' THEN NEW.number BETWEEN 1 AND 5
                                    WHEN 'lower_secondary' THEN NEW.number BETWEEN 6 AND 9
                                    WHEN 'upper_secondary' THEN NEW.number BETWEEN 10 AND 12
                                    ELSE false END) THEN
    RAISE EXCEPTION 'grade number does not fit its level' USING ERRCODE = '23514',
      CONSTRAINT = 'grade_number_fits_level';
  END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    """A class's (school, school_year, id) is the target of RoleAssignment's three-column foreign
    key (the role's school year is its class's year); the term and grade triggers lock the parent
    row they read."""

    dependencies = [
        ("schools", "0001_initial"),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="schoolclass",
            constraint=models.UniqueConstraint(
                fields=("school", "school_year", "id"), name="schoolclass_school_year_id_key"
            ),
        ),
        migrations.RunSQL(SHARE_UP, SHARE_DOWN),
    ]
