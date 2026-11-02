from datetime import date

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Account, Membership, RoleAssignment
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
)
from tenancy.models import School
from tenancy.rls import school_scope

PASSWORD = "dev-password"
# Guardians sign in by phone; a fixed number keeps the dev guardian the same on every run.
GUARDIAN_PHONE = "0912000001"


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
        "subject teacher, student and guardian, with the class, subject and student they need. "
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

        self.stdout.write(
            f"Sign in at {subdomain}.{settings.BASE_DOMAIN} with password {PASSWORD!r}:"
        )
        for role, identifier in [
            ("school_admin", f"admin@{subdomain}.test"),
            ("principal_board", f"board@{subdomain}.test"),
            ("group_leader", f"group@{subdomain}.test"),
            ("homeroom_teacher", f"homeroom@{subdomain}.test"),
            ("subject_teacher", f"subject@{subdomain}.test"),
            ("student", f"student@{subdomain}.test"),
            ("guardian", GUARDIAN_PHONE),
        ]:
            self.stdout.write(f"  {role:18} {identifier}")
