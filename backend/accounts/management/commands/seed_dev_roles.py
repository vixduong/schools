from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Account, Membership, RoleAssignment
from grades.models import GradebookColumn, ScoreEntry
from grades.views import GradebooksView
from schools.models import (
    Enrollment,
    Grade,
    GuardianLink,
    Level,
    SchoolClass,
    SchoolYear,
    Student,
    Subject,
    SubjectGroup,
    SubjectLoad,
    Term,
)
from tenancy.models import School
from tenancy.rls import school_scope
from timetable.models import AttendanceMark, BellPeriod, TimetableEntry

PASSWORD = "dev-password"
# Guardians sign in by phone; a fixed number keeps the dev guardian the same on every run.
GUARDIAN_PHONE = "0912000001"
# The Guardian of two children in two classes (7A and 7B), for every state of /guardian.
GUARDIAN_OF_TWO_PHONE = "0912000002"
# 7B's morning: five periods every day of the week, so /guardian has periods whatever day it is.
MORNING_7B = (
    (time(7, 0), time(7, 45)),
    (time(7, 50), time(8, 35)),
    (time(8, 50), time(9, 35)),
    (time(9, 40), time(10, 25)),
    (time(10, 30), time(11, 15)),
)


def _account(display_name, email=None, phone=None):
    """Reuse the Account with this email or phone; the password is set only on creation."""
    try:
        return Account.objects.get_by_identifier(email or phone)
    except Account.DoesNotExist:
        account = Account(email=email, phone=phone, display_name=display_name)
        account.set_password(PASSWORD)
        account.save()
        return account


def _membership(school, account):
    return Membership.objects.get_or_create(school=school, account=account)[0]


def _role(school, membership, role, today, **fields):
    """Grant `role` unless one in force already matches; `fields` are the scope and duties."""
    if not (
        RoleAssignment.objects.in_force(on=today)
        .filter(membership=membership, role=role, **fields)
        .exists()
    ):
        RoleAssignment.objects.create(
            school=school, membership=membership, role=role, valid_from=today, **fields
        )


class Command(BaseCommand):
    help = (
        "DEV ONLY: one sign-in per role on a dev School (run create_dev_school first, or this "
        "does it): school admin, principal board, subject group leader, homeroom teacher, "
        "subject teacher, student and guardian, with the class, subject and student they need; "
        "plus a Guardian of two children (7A and 7B) with today's marks and released scores. "
        "Idempotent. Refuses to run unless DJANGO_DEBUG=1. Run with DB_ROLE=owner."
    )

    def add_arguments(self, parser):
        parser.add_argument("subdomain")

    def handle(self, *args, subdomain, **options):
        if not settings.DEBUG:
            raise CommandError("seed_dev_roles is for development only (DJANGO_DEBUG=1).")
        call_command("create_dev_school", subdomain, f"admin@{subdomain}.test", stdout=self.stdout)
        school = School.objects.get(subdomain=subdomain)
        today = timezone.localdate()

        accounts = {
            "principal": _account("Hiệu trưởng (dev)", email=f"board@{subdomain}.test"),
            "group": _account("Tổ trưởng Toán (dev)", email=f"group@{subdomain}.test"),
            "homeroom": _account("GVCN 7A (dev)", email=f"homeroom@{subdomain}.test"),
            "subject": _account("GV Toán (dev)", email=f"subject@{subdomain}.test"),
            "student": _account("Học sinh mẫu (dev)", email=f"student@{subdomain}.test"),
            "guardian": _account("Phụ huynh mẫu (dev)", phone=GUARDIAN_PHONE),
            "subject_7b": _account("GV Toán 7B (dev)", email=f"subject7b@{subdomain}.test"),
            "guardian_of_two": _account("Phụ huynh hai con (dev)", phone=GUARDIAN_OF_TWO_PHONE),
        }

        with school_scope(school.pk):
            year = SchoolYear.objects.get(school=school, starts_on__lte=today, ends_on__gte=today)
            level = Level.objects.get_or_create(school=school, kind=Level.Kind.LOWER_SECONDARY)[0]
            grade = Grade.objects.get_or_create(school=school, number=7, defaults={"level": level})[
                0
            ]
            klass = SchoolClass.objects.get_or_create(
                school=school, school_year=year, name="7A", defaults={"grade": grade}
            )[0]
            group = SubjectGroup.objects.get_or_create(school=school, name="Toán")[0]
            subject = Subject.objects.get_or_create(
                school=school, code="MATH", defaults={"name": "Toán", "subject_group": group}
            )[0]
            # Two terms, so a gradebook can be opened (the first covers the year's first months).
            for name, starts_on, ends_on in (
                ("HK I", year.starts_on, year.starts_on + timedelta(days=135)),
                ("HK II", year.starts_on + timedelta(days=136), year.ends_on - timedelta(days=90)),
            ):
                Term.objects.get_or_create(
                    school=school,
                    school_year=year,
                    name=name,
                    defaults={"starts_on": starts_on, "ends_on": ends_on},
                )
            # The periods Grade 7 has MATH a year decide the columns of a gradebook (three regular).
            SubjectLoad.objects.get_or_create(
                school=school,
                school_year=year,
                grade=grade,
                subject=subject,
                defaults={"periods_per_year": 70},
            )

            _role(
                school,
                _membership(school, accounts["principal"]),
                RoleAssignment.Role.PRINCIPAL_BOARD,
                today,
                title=RoleAssignment.Title.PRINCIPAL,
                can_reopen_gradebooks=True,
                signs_for_principal=True,
            )
            _role(
                school,
                _membership(school, accounts["group"]),
                RoleAssignment.Role.GROUP_LEADER,
                today,
                subject_group=group,
            )
            _role(
                school,
                _membership(school, accounts["homeroom"]),
                RoleAssignment.Role.HOMEROOM_TEACHER,
                today,
                school_year=year,
                school_class=klass,
            )
            _role(
                school,
                _membership(school, accounts["subject"]),
                RoleAssignment.Role.SUBJECT_TEACHER,
                today,
                school_year=year,
                subject=subject,
                school_class=klass,
            )

            # A bell schedule and the subject teacher's first period each weekday, so the teacher
            # home has something to list (the role above starts today, so the entries do too).
            if not TimetableEntry.objects.filter(school_class=klass).exists():
                first = BellPeriod.objects.get_or_create(
                    school=school,
                    school_year=year,
                    session=BellPeriod.Session.MORNING,
                    number=1,
                    defaults={"starts_at": time(7, 0), "ends_at": time(7, 45)},
                )[0]
                for weekday in range(1, 6):
                    TimetableEntry.objects.create(
                        school=school,
                        school_year=year,
                        school_class=klass,
                        weekday=weekday,
                        bell_period=first,
                        subject=subject,
                        teacher=_membership(school, accounts["subject"]),
                        valid_from=today,
                    )

            # The student's sign-in needs an Enrollment in a secondary class first (a trigger).
            student_membership = _membership(school, accounts["student"])
            student = Student.objects.filter(membership=student_membership).first()
            if student is None:
                student = Student.objects.create(
                    school=school,
                    full_name="Học sinh mẫu",
                    date_of_birth=date(2012, 5, 1),
                    gender=Student.Gender.MALE,
                )
                Enrollment.objects.create(
                    school=school,
                    student=student,
                    school_year=year,
                    school_class=klass,
                    valid_from=year.starts_on,
                    reason_started=Enrollment.ReasonStarted.NEW_YEAR,
                )
                student.membership = student_membership
                student.save()

            GuardianLink.objects.get_or_create(
                school=school,
                membership=_membership(school, accounts["guardian"]),
                student=student,
                defaults={"relation": GuardianLink.Relation.MOTHER, "valid_from": year.starts_on},
            )

            # The Guardian of two: the student above (7A) and a child in 7B, with today's marks and
            # released scores, so /guardian shows each state against the real backend.
            klass_7b = SchoolClass.objects.get_or_create(
                school=school, school_year=year, name="7B", defaults={"grade": grade}
            )[0]
            teacher_7a = _membership(school, accounts["subject"])
            teacher_7b = _membership(school, accounts["subject_7b"])
            _role(
                school,
                teacher_7b,
                RoleAssignment.Role.SUBJECT_TEACHER,
                today,
                school_year=year,
                subject=subject,
                school_class=klass_7b,
            )
            child_7b = Student.objects.filter(enrollment__school_class=klass_7b).first()
            if child_7b is None:
                child_7b = Student.objects.create(
                    school=school,
                    full_name="Học sinh 7B",
                    date_of_birth=date(2012, 9, 2),
                    gender=Student.Gender.FEMALE,
                )
                Enrollment.objects.create(
                    school=school,
                    student=child_7b,
                    school_year=year,
                    school_class=klass_7b,
                    valid_from=year.starts_on,
                    reason_started=Enrollment.ReasonStarted.NEW_YEAR,
                )
            guardian_of_two = _membership(school, accounts["guardian_of_two"])
            for child in (student, child_7b):
                GuardianLink.objects.get_or_create(
                    school=school,
                    membership=guardian_of_two,
                    student=child,
                    defaults={
                        "relation": GuardianLink.Relation.FATHER,
                        "valid_from": year.starts_on,
                    },
                )

            if not TimetableEntry.objects.filter(school_class=klass_7b).exists():
                for number, (starts_at, ends_at) in enumerate(MORNING_7B, start=1):
                    bell = BellPeriod.objects.get_or_create(
                        school=school,
                        school_year=year,
                        session=BellPeriod.Session.MORNING,
                        number=number,
                        defaults={"starts_at": starts_at, "ends_at": ends_at},
                    )[0]
                    for weekday in range(1, 8):
                        TimetableEntry.objects.create(
                            school=school,
                            school_year=year,
                            school_class=klass_7b,
                            weekday=weekday,
                            bell_period=bell,
                            subject=subject,
                            teacher=teacher_7b,
                            valid_from=today,
                        )
            # Today's marks: each status in 7B's first four periods (the fifth stays unmarked),
            # and late in 7A's first period on a weekday (7A has none at the weekend).
            todays = TimetableEntry.objects.filter(weekday=today.isoweekday())
            marks = [
                (entry, child_7b, status, teacher_7b)
                for entry, status in zip(
                    todays.filter(school_class=klass_7b).order_by("bell_period__number"),
                    AttendanceMark.Status.values,
                    strict=False,
                )
            ] + [
                (entry, student, AttendanceMark.Status.LATE, teacher_7a)
                for entry in todays.filter(school_class=klass)[:1]
            ]
            for entry, child, status, teacher in marks:
                AttendanceMark.objects.get_or_create(
                    school=school,
                    entry=entry,
                    on=today,
                    student=child,
                    defaults={"status": status, "recorded_by": teacher},
                )

            # A MATH gradebook per class in the term in force (else the last one started; none is
            # in force over the summer), opened through the API's own rule for its columns.
            # Regular 1 and 2 are released; in 7A regular 2 changed after the release and regular 3
            # holds an unreleased score, in 7B regular 2 is released empty. Explicit times: the
            # change must come strictly after the release.
            term = (
                Term.objects.filter(school_year=year, starts_on__lte=today)
                .order_by("-starts_on")
                .first()
            )
            now = timezone.now()
            before, released_at = now - timedelta(days=2), now - timedelta(days=1)
            scores_7a = [(1, "8", before), (2, "6.5", before), (3, "9", before), (2, "7.5", now)]
            for klass_, teacher, child, scores in (
                (klass, teacher_7a, student, scores_7a),
                (klass_7b, teacher_7b, child_7b, [(1, "9", before)]),
            ):
                request = SimpleNamespace(school=school, membership=teacher)
                book = GradebooksView().open(request, term, subject, klass_)
                if book is None:  # opened on an earlier run
                    continue
                regular = {
                    column.index: column
                    for column in book.gradebookcolumn_set.filter(kind=GradebookColumn.Kind.REGULAR)
                }
                for index, value, entered_at in scores:
                    ScoreEntry.objects.create(
                        school=school,
                        column=regular[index],
                        student=child,
                        value=Decimal(value),
                        entered_by=teacher,
                        entered_at=entered_at,
                    )
                GradebookColumn.objects.filter(pk__in=[regular[1].pk, regular[2].pk]).update(
                    released_at=released_at, released_by=teacher
                )

        self.stdout.write(
            f"Sign in at {subdomain}.{settings.BASE_DOMAIN} with password {PASSWORD!r}:"
        )
        for role, identifier in [
            ("school_admin", f"admin@{subdomain}.test"),
            ("principal_board", f"board@{subdomain}.test"),
            ("group_leader", f"group@{subdomain}.test"),
            ("homeroom_teacher", f"homeroom@{subdomain}.test"),
            ("subject_teacher", f"subject@{subdomain}.test"),
            ("subject_teacher", f"subject7b@{subdomain}.test"),
            ("student", f"student@{subdomain}.test"),
            ("guardian", GUARDIAN_PHONE),
            ("guardian", GUARDIAN_OF_TWO_PHONE),
        ]:
            self.stdout.write(f"  {role:18} {identifier}")
