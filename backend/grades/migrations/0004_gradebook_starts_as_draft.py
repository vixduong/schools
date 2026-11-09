from django.db import migrations

# `gradebook_lifecycle` runs on UPDATE of the status only: an INSERT as submitted or approved would
# skip every rule of the workflow. A gradebook starts as a draft; the status then follows a step.
# (An unknown status stays for `gradebook_status_is_known`.)
STARTS_UP = """
CREATE FUNCTION gradebook_starts_as_draft() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IN ('submitted', 'approved') THEN
    RAISE EXCEPTION 'a gradebook starts as a draft' USING ERRCODE = '23514',
      CONSTRAINT = 'gradebook_starts_as_draft';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER gradebook_starts_as_draft BEFORE INSERT ON grades_gradebook
  FOR EACH ROW EXECUTE FUNCTION gradebook_starts_as_draft();
"""
STARTS_DOWN = """
DROP TRIGGER gradebook_starts_as_draft ON grades_gradebook;
DROP FUNCTION gradebook_starts_as_draft();
"""


class Migration(migrations.Migration):

    dependencies = [("grades", "0003_gradebook_workflow")]

    operations = [migrations.RunSQL(STARTS_UP, STARTS_DOWN)]
