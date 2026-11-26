import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.management.commands.seed_dev_roles import (
    GUARDIAN_OF_TWO_PHONE,
    GUARDIAN_PHONE,
    PASSWORD,
)
from grades.models import Gradebook
from grades.tests.conftest import profile_versions  # noqa: F401 (the fixture, used below)
from schools.models import Enrollment, GuardianLink, Student, SubjectLoad, Term
from tenancy.models import School
from tenancy.rls import school_scope
from testing import db_role
from timetable.models import TimetableEntry

# The seed opens gradebooks, which need the profile versions a transactional test flushes.
pytestmark = pytest.mark.usefixtures("profile_versions")


@pytest.mark.parametrize(
    ("identifier", "roles"),
    [
        ("admin@c.test", ["school_admin"]),
        ("board@c.test", ["principal_board"]),
        ("group@c.test", ["group_leader"]),
        ("homeroom@c.test", ["homeroom_teacher"]),
        ("subject@c.test", ["subject_teacher"]),
        ("subject7b@c.test", ["subject_teacher"]),
        ("student@c.test", []),
        (GUARDIAN_PHONE, []),
        (GUARDIAN_OF_TWO_PHONE, []),
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
    with school_scope(School.objects.get(subdomain="c").pk):
        student, child_7b = Student.objects.order_by("membership")
        assert student.membership is not None
        assert child_7b.membership is None
        assert Enrollment.objects.filter(student=student).count() == 1
        assert Enrollment.objects.filter(student=child_7b).count() == 1
        assert GuardianLink.objects.filter(student=student).count() == 2  # both guardians
        assert GuardianLink.objects.filter(student=child_7b).count() == 1
        # Once, however often the seed runs: 7A's first period Mon-Fri, 7B's five every day.
        assert TimetableEntry.objects.count() == 5 + 5 * 7
        assert Gradebook.objects.count() == 2
        assert SubjectLoad.objects.count() == 1  # Grade 7 x MATH, once
        assert Term.objects.count() == 2


def test_guardian_of_two_sees_every_portal_state(client, schools, settings):
    settings.DEBUG = True
    call_command("seed_dev_roles", "c")
    call_command("seed_dev_roles", "c")
    with school_scope(School.objects.get(subdomain="c").pk):
        # Explicit: from June to August no term is in force, so the default term is none.
        term = Gradebook.objects.get(school_class__name="7A").term_id
    with db_role(settings.APP_DB_USER, settings.APP_DB_PASSWORD):
        login = {"identifier": GUARDIAN_OF_TWO_PHONE, "password": PASSWORD}
        response = client.post(
            "/api/auth/login/", login, content_type="application/json", HTTP_HOST="c.localhost"
        )
        assert response.status_code == 200

        def get(path):
            response = client.get(f"/api/portal/{path}", HTTP_HOST="c.localhost")
            assert response.status_code == 200, response.content
            return response.json()

        children = {child["class_name"]: child for child in get("children/")}
        assert sorted(children) == ["7A", "7B"]
        assert not any(child["left"] for child in children.values())
        day = get(f"children/{children['7B']['id']}/today/")
        assert [period["status"] for period in day["periods"]] == [
            "present",
            "late",
            "absent_excused",
            "absent_unexcused",
            None,
        ]

        def released(klass):
            (book,) = get(f"children/{children[klass]['id']}/scores/?term={term}")["gradebooks"]
            return [
                (c["kind"], c["index"], c["value"], c["changed_after_release"])
                for c in book["columns"]
            ]

        # 7A's regular 3 holds a score but is not released, so it is absent.
        assert released("7A") == [("regular", 1, 8.0, False), ("regular", 2, 7.5, True)]
        assert released("7B") == [("regular", 1, 9.0, False), ("regular", 2, None, False)]


def test_refuses_outside_debug(schools, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="development only"):
        call_command("seed_dev_roles", "c")
