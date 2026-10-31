from rest_framework import serializers

from accounts.models import RoleAssignment

from .models import Grade, Level, Room, SchoolClass, SchoolYear, Subject, SubjectGroup, Term


class CurrentSchool:
    """Default for the hidden `school` field: the School of the request. Having `school` among
    the serializer fields also lets DRF build the (school, ...) unique validators."""

    requires_context = True

    def __call__(self, serializer_field):
        return serializer_field.context["request"].school


class SetupSerializer(serializers.ModelSerializer):
    school = serializers.HiddenField(default=CurrentSchool())


def setup_serializer(model, *fields, name=None):
    meta = type("Meta", (), {"model": model, "fields": ["school", "id", *fields]})
    return type(name or f"{model.__name__}Serializer", (SetupSerializer,), {"Meta": meta})


SchoolYearSerializer = setup_serializer(SchoolYear, "name", "starts_on", "ends_on")
TermSerializer = setup_serializer(Term, "school_year", "name", "starts_on", "ends_on")
LevelSerializer = setup_serializer(Level, "kind")
GradeSerializer = setup_serializer(Grade, "level", "number")
SubjectGroupSerializer = setup_serializer(SubjectGroup, "name")
SubjectSerializer = setup_serializer(
    Subject, "name", "code", "subject_group", "ministry_code", "assessment", "is_active"
)
RoomSerializer = setup_serializer(Room, "name", "is_active")
SchoolClassSerializer = setup_serializer(SchoolClass, "school_year", "grade", "name", "room")


class RoleAssignmentSetupSerializer(SetupSerializer):
    """Who holds which duty, where and when. Only the period can change afterwards: to end a role
    set `valid_to`; to resume it later, create a new assignment."""

    IMMUTABLE = ("membership", "role", "school_year", "subject_group", "school_class", "subject")

    class Meta:
        model = RoleAssignment
        fields = [
            "school",
            "id",
            "membership",
            "role",
            "school_year",
            "subject_group",
            "school_class",
            "subject",
            "valid_from",
            "valid_to",
        ]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            for name in self.IMMUTABLE:
                fields[name].read_only = True
        return fields
