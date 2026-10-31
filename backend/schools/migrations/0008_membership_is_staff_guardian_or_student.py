from django.db import migrations

# A student's sign-in Membership holds no RoleAssignment and no GuardianLink, and a Membership with
# one of those cannot become a student's. The serializers check it first; these triggers keep it
# true for every writer. The Membership row is where the two sides meet: the role/link side locks
# it FOR SHARE (many may at once), the student side FOR NO KEY UPDATE (which conflicts), so a
# role being given and a student sign-in being set on the same Membership at the same moment
# cannot both miss the other's uncommitted row; the check runs after the lock is granted, on a
# fresh snapshot (as in schools.0002).
UP = """
CREATE FUNCTION membership_is_not_a_student() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM accounts_membership m
   WHERE m.school_id = NEW.school_id AND m.id = NEW.membership_id FOR SHARE;
  PERFORM 1 FROM schools_student s
   WHERE s.school_id = NEW.school_id AND s.membership_id = NEW.membership_id;
  IF FOUND THEN
    RAISE EXCEPTION 'a student''s membership holds no role assignment and no guardian link'
      USING ERRCODE = '23514', CONSTRAINT = TG_ARGV[0];
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER roleassignment_membership_is_not_a_student
  BEFORE INSERT OR UPDATE OF membership_id ON accounts_roleassignment
  FOR EACH ROW EXECUTE FUNCTION membership_is_not_a_student('roleassignment_membership_is_not_a_student');
CREATE TRIGGER guardianlink_membership_is_not_a_student
  BEFORE INSERT OR UPDATE OF membership_id ON schools_guardianlink
  FOR EACH ROW EXECUTE FUNCTION membership_is_not_a_student('guardianlink_membership_is_not_a_student');

CREATE FUNCTION student_membership_holds_no_role_or_link() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.membership_id IS NOT NULL THEN
    PERFORM 1 FROM accounts_membership m
     WHERE m.school_id = NEW.school_id AND m.id = NEW.membership_id FOR NO KEY UPDATE;
    PERFORM 1 FROM accounts_roleassignment r
     WHERE r.school_id = NEW.school_id AND r.membership_id = NEW.membership_id;
    IF FOUND THEN
      RAISE EXCEPTION 'a membership with a role assignment cannot be a student''s sign-in'
        USING ERRCODE = '23514', CONSTRAINT = 'student_membership_has_no_role_assignment';
    END IF;
    PERFORM 1 FROM schools_guardianlink g
     WHERE g.school_id = NEW.school_id AND g.membership_id = NEW.membership_id;
    IF FOUND THEN
      RAISE EXCEPTION 'a membership with a guardian link cannot be a student''s sign-in'
        USING ERRCODE = '23514', CONSTRAINT = 'student_membership_has_no_guardian_link';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER student_membership_holds_no_role_or_link
  BEFORE INSERT OR UPDATE OF membership_id ON schools_student
  FOR EACH ROW EXECUTE FUNCTION student_membership_holds_no_role_or_link();
"""

DOWN = """
DROP TRIGGER student_membership_holds_no_role_or_link ON schools_student;
DROP FUNCTION student_membership_holds_no_role_or_link();
DROP TRIGGER guardianlink_membership_is_not_a_student ON schools_guardianlink;
DROP TRIGGER roleassignment_membership_is_not_a_student ON accounts_roleassignment;
DROP FUNCTION membership_is_not_a_student();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0007_secondary_profile_from_2024"),
        ("accounts", "0009_one_principal_at_a_time"),
    ]

    operations = [migrations.RunSQL(UP, DOWN)]
