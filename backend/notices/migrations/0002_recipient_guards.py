from django.db import migrations

# The one place the four audiences are defined (docs/slices/1a-slice-7.md): does this notice reach
# this Membership? STABLE and SECURITY INVOKER, so RLS applies to every table it reads. "Today" is
# the School's day, not the database session's (UTC). The Membership must be active and is never
# the notice's sender, so every writer, not only the send service, is held to both. "In force" is
# the Python `Enrollment.objects.in_force` / `RoleAssignment.objects.in_force` and the Guardian's
# `Actor.linked_student_ids` rule; a test compares them.
REACHES_UP = """
CREATE FUNCTION notice_reaches(p_notice_id bigint, p_membership_id bigint) RETURNS boolean
LANGUAGE plpgsql STABLE AS $$
DECLARE
  n notices_notice%ROWTYPE;
  today date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
  SELECT * INTO n FROM notices_notice WHERE id = p_notice_id;
  IF NOT FOUND OR n.sender_id = p_membership_id THEN
    RETURN false;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_membership m
                  WHERE m.school_id = n.school_id AND m.id = p_membership_id
                    AND m.status = 'active') THEN
    RETURN false;
  END IF;
  IF n.audience = 'group' THEN
    RETURN EXISTS (
      SELECT 1 FROM accounts_roleassignment ra
        JOIN schools_subject s ON s.school_id = ra.school_id AND s.id = ra.subject_id
       WHERE ra.school_id = n.school_id AND ra.membership_id = p_membership_id
         AND ra.role = 'subject_teacher' AND ra.status = 'active'
         AND ra.valid_from <= today AND (ra.valid_to IS NULL OR ra.valid_to >= today)
         AND s.subject_group_id = n.subject_group_id);
  END IF;
  -- school: every student enrolled today; homeroom_guardians and class: those of the class.
  -- The Guardians of such a student, and (not for homeroom_guardians) the student themself.
  RETURN EXISTS (
    SELECT 1 FROM schools_enrollment en
      JOIN schools_schoolyear y ON y.school_id = en.school_id AND y.id = en.school_year_id
     WHERE en.school_id = n.school_id
       AND en.valid_from <= today AND (en.valid_to IS NULL OR en.valid_to >= today)
       AND y.starts_on <= today AND y.ends_on >= today
       AND (n.audience = 'school' OR en.school_class_id = n.school_class_id)
       AND (EXISTS (SELECT 1 FROM schools_guardianlink g
                     WHERE g.school_id = en.school_id AND g.student_id = en.student_id
                       AND g.membership_id = p_membership_id
                       AND g.valid_from <= today AND (g.valid_to IS NULL OR g.valid_to >= today))
            OR (n.audience <> 'homeroom_guardians'
                AND EXISTS (SELECT 1 FROM schools_student st
                             WHERE st.school_id = en.school_id AND st.id = en.student_id
                               AND st.membership_id = p_membership_id))));
END $$;
"""
REACHES_DOWN = "DROP FUNCTION notice_reaches(bigint, bigint)"

# A recipient is someone the notice reaches. Reported like a constraint (23514).
IN_AUDIENCE_UP = """
CREATE FUNCTION noticerecipient_is_in_audience() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT notice_reaches(NEW.notice_id, NEW.membership_id) THEN
    RAISE EXCEPTION 'a notice reaches only the people of its audience, never its sender'
      USING ERRCODE = '23514', CONSTRAINT = 'noticerecipient_is_in_audience';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER noticerecipient_is_in_audience BEFORE INSERT ON notices_noticerecipient
  FOR EACH ROW EXECUTE FUNCTION noticerecipient_is_in_audience();
"""
IN_AUDIENCE_DOWN = """
DROP TRIGGER noticerecipient_is_in_audience ON notices_noticerecipient;
DROP FUNCTION noticerecipient_is_in_audience();
"""

# The recipient and the notice never change, and a stamp, once set, is never overwritten (a
# column grant alone would allow it). Who may mark a read is the API's rule: the caller's own row.
SET_ONCE_UP = """
CREATE FUNCTION noticerecipient_set_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.school_id, NEW.notice_id, NEW.membership_id)
       IS DISTINCT FROM (OLD.school_id, OLD.notice_id, OLD.membership_id)
     OR (OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at)
     OR (OLD.emailed_at IS NOT NULL AND NEW.emailed_at IS DISTINCT FROM OLD.emailed_at) THEN
    RAISE EXCEPTION 'a recipient row never changes, and a stamp is set once'
      USING ERRCODE = '23514', CONSTRAINT = 'noticerecipient_set_once';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER noticerecipient_set_once BEFORE UPDATE ON notices_noticerecipient
  FOR EACH ROW EXECUTE FUNCTION noticerecipient_set_once();
"""
SET_ONCE_DOWN = """
DROP TRIGGER noticerecipient_set_once ON notices_noticerecipient;
DROP FUNCTION noticerecipient_set_once();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("notices", "0001_notices"),
    ]

    operations = [
        migrations.RunSQL(REACHES_UP, REACHES_DOWN),
        migrations.RunSQL(IN_AUDIENCE_UP, IN_AUDIENCE_DOWN),
        migrations.RunSQL(SET_ONCE_UP, SET_ONCE_DOWN),
    ]
