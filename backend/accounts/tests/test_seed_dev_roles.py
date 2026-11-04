import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.management.commands.seed_dev_roles import GUARDIAN_PHONE, PASSWORD
from schools.models import Enrollment, GuardianLink, Student
from timetable.models import TimetableEntry


@pytest.mark.parametrize(
    ("identifier", "roles"),
    [
        ("admin@c.test", ["school_admin"]),
        ("board@c.test", ["principal_board"]),
        ("group@c.test", ["group_leader"]),
        ("homeroom@c.test", ["homeroom_teacher"]),
        ("subject@c.test", ["subject_teacher"]),
        ("student@c.test", []),
        (GUARDIAN_PHONE, []),
    ],
)
def test_each_role_signs_in_with_its_role(client, schools, settings, identifier, roles):
    settings.DEBUG = True
    call_command("seed_dev_roles", "c")
    call_command("seed_dev_roles", "c")  # idempotent
    response = client.post(
        "/api/auth/login/",
        {"identifier": identifier, "password": PASSWORD},
        content_type="application/json",
        HTTP_HOST="c.localhost",
    )
    assert response.status_code == 200
    assert [r["role"] for r in response.json()["role_assignments"]] == roles


def test_student_and_guardian_are_linked(schools, settings):
    settings.DEBUG = True
    call_command("seed_dev_roles", "c")
    call_command("seed_dev_roles", "c")
    from tenancy.models import School
    from tenancy.rls import school_scope

    with school_scope(School.objects.get(subdomain="c").pk):
        (student,) = Student.objects.all()
        assert student.membership is not None
        assert Enrollment.objects.filter(student=student).count() == 1
        assert GuardianLink.objects.filter(student=student).count() == 1
        assert TimetableEntry.objects.count() == 5  # once, however often the seed runs


def test_refuses_outside_debug(schools, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="development only"):
        call_command("seed_dev_roles", "c")
