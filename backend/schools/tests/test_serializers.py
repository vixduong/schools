"""Who sees a student's sensitive fields (`student_profile.view_sensitive`)."""

import pytest

from permissions.tests.conftest import world  # noqa: F401
from schools.models import Student
from schools.serializers import StudentListSerializer, StudentSerializer

SENSITIVE = {"national_id", "ministry_student_id"}


class FakeRequest:
    def __init__(self, membership):
        self.membership = membership
        self.school = membership.school


@pytest.mark.parametrize("serializer", [StudentSerializer, StudentListSerializer])
def test_only_the_homeroom_teacher_the_board_and_the_admin_see_sensitive_fields(world, serializer):  # noqa: F811
    for number, student in enumerate((world.targets["student_s1"], world.targets["student_s2"])):
        Student.objects.filter(pk=student.pk).update(
            national_id=f"01234567890{number}", ministry_student_id=f"VN{number}"
        )
    seen = {}
    for role, actor in world.actors.items():
        context = {"request": FakeRequest(actor.membership)}
        for name in ("student_s1", "student_s2"):
            student = Student.objects.get(pk=world.targets[name].pk)
            data = serializer(student, context=context).data
            assert SENSITIVE <= set(data) or not SENSITIVE & set(data), (role, name)
            seen[(role, name)] = SENSITIVE <= set(data)
    assert {key for key, shown in seen.items() if shown} == {
        ("school_admin", "student_s1"),
        ("school_admin", "student_s2"),
        ("principal_board", "student_s1"),
        ("principal_board", "student_s2"),
        ("homeroom_teacher", "student_s1"),  # their own class only
    }
