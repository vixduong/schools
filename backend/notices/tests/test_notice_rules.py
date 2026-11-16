"""The database rules of a Notice and its recipients: who an audience reaches (`notice_reaches`),
the checks, the append-only grants, the set-once read mark, the audit and RLS."""

import pytest
from django.db import IntegrityError, ProgrammingError, connection
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from audit.models import AuditEvent
from notices.models import Notice, NoticeRecipient
from notices.services import create_notice
from permissions.actor import Actor
from schools.models import Enrollment, GuardianLink, SchoolYear, Student
from schools.tests.factories import make_class, make_group, make_student, make_subject
from tenancy.rls import school_scope
from testing import make_account

from .conftest import DAY, TODAY, Role, assign, link

Audience = Notice.Audience
AUDIENCES = {
    # name: (sender, audience, target, who is reached)
    "school": (
        "admin",
        Audience.SCHOOL,
        None,
        {"g_an", "s_an", "g_binh", "s_binh", "g_chi", "hr_7a"},
    ),
    "group": ("gl_math", Audience.GROUP, "math_group", {"t_math"}),
    "homeroom_guardians": ("hr_7a", Audience.HOMEROOM_GUARDIANS, "7A", {"g_an", "g_chi"}),
    "class": ("t_math", Audience.CLASS, "7A", {"g_an", "s_an", "g_chi", "hr_7a"}),
    "class_7b": ("t_lit", Audience.CLASS, "7B", {"g_binh", "s_binh"}),
}


def target_of(world, audience, target):
    if target is None:
        return {}
    column = "subject_group" if audience == Audience.GROUP else "school_class"
    return {column: world[target]}


def send(world, sender, audience, target=None, **fields):
    """A Notice and its recipients, as the send view makes them. Inside a School scope."""
    return create_notice(
        school=world["school"],
        sender=world["m"][sender],
        audience=audience,
        title=fields.pop("title", "Họp phụ huynh"),
        body=fields.pop("body", "Thứ Bảy, 8 giờ."),
        **target_of(world, audience, target),
    )


def recipient_names(world, notice):
    by_id = {m.pk: n for n, m in world["m"].items()}
    ids = NoticeRecipient.objects.filter(notice=notice).values_list("membership_id", flat=True)
    return {by_id[i] for i in ids}


@pytest.mark.parametrize("case", AUDIENCES)
def test_an_audience_reaches_exactly_its_recipients(world, case):
    sender, audience, target, expected = AUDIENCES[case]
    with school_scope(world["school"].pk):
        notice = send(world, sender, audience, target)
        assert recipient_names(world, notice) == expected


def reference(world, notice):
    """The same rules in Python: Enrollment and RoleAssignment `in_force`, and the Guardian's
    `Actor.linked_student_ids`."""
    memberships = Membership.objects.filter(status=Membership.Status.ACTIVE).exclude(
        pk=notice.sender_id
    )
    enrolled = Enrollment.objects.in_force(TODAY)
    if notice.school_class_id:
        enrolled = enrolled.filter(school_class_id=notice.school_class_id)
    students = set(enrolled.values_list("student_id", flat=True))
    if notice.audience == Audience.GROUP:
        teachers = group_teachers(notice.subject_group_id)
        return {m.pk for m in memberships if m.pk in teachers}
    guardians = {m.pk for m in memberships if Actor(m, TODAY).linked_student_ids & students}
    if notice.audience == Audience.HOMEROOM_GUARDIANS:
        return guardians
    own = set(
        m.pk
        for m in memberships
        if m.student_set.filter(pk__in=students).exists()  # Student.membership
    )
    return guardians | own


def group_teachers(group_id):
    return set(
        RoleAssignment.objects.in_force(TODAY)
        .filter(role=Role.SUBJECT_TEACHER, subject__subject_group_id=group_id)
        .values_list("membership_id", flat=True)
    )


@pytest.mark.parametrize("case", AUDIENCES)
def test_notice_reaches_agrees_with_the_python_helpers_for_every_membership(world, case):
    sender, audience, target, _ = AUDIENCES[case]
    with school_scope(world["school"].pk):
        notice = send(world, sender, audience, target)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT m.id FROM accounts_membership m WHERE notice_reaches(%s, m.id)",
                [notice.pk],
            )
            in_sql = {row[0] for row in cursor.fetchall()}
        assert in_sql == reference(world, notice)
        assert in_sql == {world["m"][n].pk for n in AUDIENCES[case][3]}


@pytest.fixture
def between_years(schools):
    """School B on the first day of its new school year, the last year having ended yesterday.
    Alongside the people who count today (g_cur and s_cur of class 8A, t_cur teaching it) are the
    ones who look in but do not: an Enrollment open (no valid_to) in the year that ended
    yesterday, with a Guardian (g_old) and a student Account (s_old); and a GuardianLink, an
    Enrollment and a RoleAssignment that all start tomorrow."""
    b = schools[1]
    names = (
        "admin",
        "g_cur",
        "s_cur",
        "t_cur",
        "g_old",
        "s_old",
        "g_link_future",
        "g_enrol_future",
        "s_enrol_future",
        "t_future",
    )
    accounts = {n: make_account(f"{n}@b.example.com", display_name=n) for n in names}
    with school_scope(b.pk):
        m = {n: Membership.objects.create(school=b, account=accounts[n]) for n in names}
        last = SchoolYear.objects.create(
            school=b, name="last", starts_on=TODAY - 300 * DAY, ends_on=TODAY - DAY
        )
        year = SchoolYear.objects.create(
            school=b, name="now", starts_on=TODAY, ends_on=TODAY + 300 * DAY
        )
        old_class, klass = make_class(b, last, "7A"), make_class(b, year, "8A")
        group = make_group(b, "Math")
        math = make_subject(b, "MATH", group)

        def student(name, account_name, in_class, valid_from, guardian):
            person = make_student(b, name)
            Enrollment.objects.create(
                school=b,
                student=person,
                school_year=in_class.school_year,
                school_class=in_class,
                valid_from=valid_from,
                reason_started=Enrollment.ReasonStarted.NEW_YEAR,
            )
            Student.objects.filter(pk=person.pk).update(membership=m[account_name])
            link(b, m[guardian], person)
            return person

        current = student("Cur", "s_cur", klass, TODAY, "g_cur")
        student("Old", "s_old", old_class, TODAY - 200 * DAY, "g_old")  # no valid_to
        student("Soon", "s_enrol_future", klass, TODAY + DAY, "g_enrol_future")
        GuardianLink.objects.create(  # a second Guardian of a student enrolled today
            school=b,
            membership=m["g_link_future"],
            student=current,
            relation=GuardianLink.Relation.FATHER,
            valid_from=TODAY + DAY,
        )
        assign(b, m["admin"], Role.SCHOOL_ADMIN)
        assign(b, m["t_cur"], Role.SUBJECT_TEACHER, subject=math, school_class=klass)
        assign(b, m["t_future"], Role.SUBJECT_TEACHER, subject=math, school_class=klass)
        RoleAssignment.objects.filter(membership=m["t_future"]).update(valid_from=TODAY + DAY)
    return {"school": b, "m": m, "class": klass, "group": group}


OUTSIDE = (
    "g_old",
    "s_old",
    "g_link_future",
    "g_enrol_future",
    "s_enrol_future",
    "t_future",
)


@pytest.mark.parametrize(
    ("audience", "target", "expected"),
    [
        (Audience.SCHOOL, None, {"g_cur", "s_cur"}),
        (Audience.GROUP, "group", {"t_cur"}),
        (Audience.HOMEROOM_GUARDIANS, "class", {"g_cur"}),
        (Audience.CLASS, "class", {"g_cur", "s_cur"}),
    ],
)
def test_nobody_outside_today_or_the_school_year_is_reached_by_sql_or_python(
    between_years, audience, target, expected
):
    scene = between_years
    with school_scope(scene["school"].pk):
        notice = send(scene, "admin", audience, target)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT m.id FROM accounts_membership m WHERE notice_reaches(%s, m.id)",
                [notice.pk],
            )
            in_sql = {row[0] for row in cursor.fetchall()}
        in_python = reference(scene, notice)
    assert in_sql == in_python == {scene["m"][n].pk for n in expected}
    assert not in_sql & {scene["m"][n].pk for n in OUTSIDE}


def recipient(world, notice, name):
    return NoticeRecipient(school=world["school"], notice=notice, membership=world["m"][name])


@pytest.mark.parametrize(
    "who",
    ["admin", "g_an_ended", "g_dao", "g_eve", "g_inactive", "s_dao", "t_math", "nobody"],
)
def test_the_trigger_refuses_a_recipient_outside_the_audience(world, who):
    """A Guardian whose link ended, a student who left, a Guardian between years, an inactive
    Membership, a teacher: none is in the homeroom's Guardians. The sender is refused too."""
    school = world["school"]
    with school_scope(school.pk):
        notice = send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A")
    with pytest.raises(IntegrityError, match="noticerecipient_is_in_audience"):
        with school_scope(school.pk):
            recipient(world, notice, who).save()


def test_the_trigger_refuses_the_sender_and_an_inactive_membership(world):
    school = world["school"]
    with school_scope(school.pk):
        notice = send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A")
    for who in ("hr_7a", "g_inactive"):  # hr_7a is also a Guardian of Chi, in 7A
        with pytest.raises(IntegrityError, match="noticerecipient_is_in_audience"):
            with school_scope(school.pk):
                recipient(world, notice, who).save()


def test_a_pending_or_ended_role_assignment_or_inactive_teacher_is_not_in_a_group(world):
    with school_scope(world["school"].pk):
        notice = send(world, "gl_math", Audience.GROUP, "math_group")
        assert recipient_names(world, notice) == {"t_math"}


def notice_fields(world, **fields):
    base = {
        "school": world["school"],
        "sender": world["m"]["admin"],
        "audience": Audience.SCHOOL,
        "title": "Tiêu đề",
        "body": "Nội dung",
    }
    return {**base, **fields}


@pytest.mark.parametrize(
    ("constraint", "fields"),
    [
        ("notice_audience_is_known", {"audience": "everyone"}),
        ("notice_target_fits_audience", {"school_class": "7A"}),  # school: neither column
        ("notice_target_fits_audience", {"audience": Audience.GROUP}),  # group: needs a group
        (
            "notice_target_fits_audience",
            {"audience": Audience.GROUP, "subject_group": "math_group", "school_class": "7A"},
        ),
        ("notice_target_fits_audience", {"audience": Audience.CLASS}),  # class: needs a class
        (
            "notice_target_fits_audience",
            {"audience": Audience.HOMEROOM_GUARDIANS, "subject_group": "math_group"},
        ),
        ("notice_title_not_blank", {"title": "  "}),
        ("notice_title_single_line", {"title": "a\nb"}),
        ("notice_title_single_line", {"title": "a\rb"}),
        ("notice_body_not_blank", {"body": " \n "}),
        ("notice_body_length", {"body": "x" * 5001}),
    ],
)
def test_a_notice_is_checked(world, constraint, fields):
    resolved = {k: world[v] if v in ("7A", "7B", "math_group") else v for k, v in fields.items()}
    with pytest.raises(IntegrityError, match=constraint):
        with school_scope(world["school"].pk):
            Notice.objects.create(**notice_fields(world, **resolved))


def test_a_body_of_5000_characters_is_accepted(world):
    with school_scope(world["school"].pk):
        Notice.objects.create(**notice_fields(world, body="x" * 5000))


def test_a_notice_points_only_at_its_own_schools_rows(schools, world):
    account = make_account("b@example.com")
    with school_scope(schools[1].pk):
        other = Membership.objects.create(school=schools[1], account=account)
    with pytest.raises(IntegrityError, match="notice_sender_id_same_school"):
        with school_scope(world["school"].pk):
            Notice.objects.create(**notice_fields(world, sender=other))


def test_a_recipient_is_listed_once(world):
    with school_scope(world["school"].pk):
        notice = send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A")
    with pytest.raises(IntegrityError, match="noticerecipient_once_per_notice"):
        with school_scope(world["school"].pk):
            recipient(world, notice, "g_an").save()


@pytest.mark.usefixtures("as_app_role")
class TestAsTheAppRole:
    def test_a_sent_notice_is_never_edited_or_deleted(self, world):
        with school_scope(world["school"].pk):
            notice = send(world, "admin", Audience.SCHOOL)
        for sql in (
            "UPDATE notices_notice SET title = 'khác' WHERE id = %s",
            "DELETE FROM notices_notice WHERE id = %s",
        ):
            with pytest.raises(ProgrammingError), school_scope(world["school"].pk):
                connection.cursor().execute(sql, [notice.pk])

    def test_a_recipient_row_changes_only_its_two_stamps_and_is_never_deleted(self, world):
        with school_scope(world["school"].pk):
            notice = send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A")
            mine = NoticeRecipient.objects.filter(notice=notice, membership=world["m"]["g_an"])
            assert mine.update(read_at=timezone.now(), emailed_at=timezone.now()) == 1
        for sql in (
            "UPDATE notices_noticerecipient SET membership_id = membership_id WHERE notice_id = %s",
            "UPDATE notices_noticerecipient SET notice_id = notice_id WHERE notice_id = %s",
            "DELETE FROM notices_noticerecipient WHERE notice_id = %s",
        ):
            with pytest.raises(ProgrammingError), school_scope(world["school"].pk):
                connection.cursor().execute(sql, [notice.pk])

    def test_a_read_mark_is_set_once(self, world):
        school = world["school"]
        with school_scope(school.pk):
            notice = send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A")
            mine = NoticeRecipient.objects.filter(notice=notice, membership=world["m"]["g_an"])
            assert mine.filter(read_at__isnull=True).update(read_at=timezone.now()) == 1
        for stamp in ("read_at", "emailed_at"):
            if stamp == "emailed_at":
                with school_scope(school.pk):
                    mine.update(emailed_at=timezone.now())
            with pytest.raises(IntegrityError, match="noticerecipient_set_once"):
                with school_scope(school.pk):
                    mine.update(**{stamp: timezone.now()})

    def test_a_school_sees_nothing_of_another_schools_notices(self, schools, world):
        with school_scope(world["school"].pk):
            send(world, "admin", Audience.SCHOOL)
            assert Notice.objects.count() == 1
            assert NoticeRecipient.objects.count() == 6
        with school_scope(schools[1].pk):
            assert Notice.objects.count() == 0
            assert NoticeRecipient.objects.count() == 0


def test_the_trigger_freezes_the_identity_of_a_recipient_row(world):
    """As the owner (who may update every column): school, notice and membership never change."""
    school = world["school"]
    with school_scope(school.pk):
        notice = send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A")
    for column, value in (("membership_id", world["m"]["g_chi"].pk), ("notice_id", notice.pk + 1)):
        with pytest.raises(IntegrityError, match="noticerecipient_set_once"):
            with school_scope(school.pk):
                NoticeRecipient.objects.filter(notice=notice, membership=world["m"]["g_an"]).update(
                    **{column: value}
                )


def test_a_sent_notice_is_audited_without_its_title_or_body(world):
    school = world["school"]
    with school_scope(school.pk):
        notice = send(
            world, "t_math", Audience.CLASS, "7A", title="Bí mật tiêu đề", body="Bí mật nội dung"
        )
        events = list(AuditEvent.objects.filter(target_table="notices_notice"))
        assert not AuditEvent.objects.filter(target_table="notices_noticerecipient").exists()
    (event,) = events
    assert (event.action, event.target_id) == ("insert", notice.pk)
    assert event.details["audience"] == "class"
    assert event.details["school_class_id"] == world["7A"].pk
    assert event.details["sender_id"] == world["m"]["t_math"].pk
    assert "title" not in event.details and "body" not in event.details
    assert "Bí mật" not in str(event.details)
