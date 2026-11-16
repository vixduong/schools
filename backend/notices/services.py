from django.db import connection

from .models import Notice, NoticeRecipient


def create_notice(*, school, sender, audience, title, body, school_class=None, subject_group=None):
    """The Notice and its recipients: every active Membership of the School the database says
    the audience reaches (`notice_reaches`), so Python never re-implements the audience rules.
    Call inside the School's scope. The caller decides whether nobody reached is an error."""
    notice = Notice.objects.create(
        school=school,
        sender=sender,
        audience=audience,
        school_class=school_class,
        subject_group=subject_group,
        title=title,
        body=body,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {NoticeRecipient._meta.db_table} (school_id, notice_id, membership_id) "
            "SELECT %s, %s, m.id FROM accounts_membership m "
            "WHERE m.school_id = %s AND notice_reaches(%s, m.id)",
            [school.pk, notice.pk, school.pk, notice.pk],
        )
        notice.recipient_count = cursor.rowcount
    return notice
