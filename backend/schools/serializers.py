from django.utils import timezone
from rest_framework import serializers

from accounts.models import Membership, RoleAssignment

from .models import Grade, Level, Room, SchoolClass, SchoolYear, Subject, SubjectGroup, Term


class CurrentSchool:
    """Default for the hidden `school` field: the School of the request. Having `school` among
    the serializer fields also lets DRF build the (school, ...) unique validators."""

    requires_context = True

    def __call__(self, serializer_field):
        return serializer_field.context["request"].school


class SetupSerializer(serializers.ModelSerializer):
    """`IMMUTABLE` fields are read-only once the row exists (ignored on update)."""

    IMMUTABLE: tuple[str, ...] = ()

    school = serializers.HiddenField(default=CurrentSchool())

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            for name in self.IMMUTABLE:
                fields[name].read_only = True
        return fields


def setup_serializer(model, *fields, name=None, immutable=()):
    meta = type("Meta", (), {"model": model, "fields": ["school", "id", *fields]})
    attrs = {"Meta": meta, "IMMUTABLE": immutable}
    return type(name or f"{model.__name__}Serializer", (SetupSerializer,), attrs)


SchoolYearSerializer = setup_serializer(SchoolYear, "name", "starts_on", "ends_on")
TermSerializer = setup_serializer(Term, "school_year", "name", "starts_on", "ends_on")
LevelSerializer = setup_serializer(Level, "kind")
# A grade's number and level never change; a class never moves to another year or grade.
GradeSerializer = setup_serializer(Grade, "level", "number", immutable=("level", "number"))
SubjectGroupSerializer = setup_serializer(SubjectGroup, "name")


SubjectSerializer = setup_serializer(
    Subject, "name", "code", "subject_group", "ministry_code", "assessment", "is_active"
)
RoomSerializer = setup_serializer(Room, "name", "is_active")


class SchoolClassSerializer(
    setup_serializer(
        SchoolClass,
        "school_year",
        "grade",
        "name",
        "room",
        immutable=("school_year", "grade"),
        name="SchoolClassBase",
    )
):
    def validate_room(self, room):
        """An inactive room is no new target; a class may keep the one it already has."""
        if room is not None and not room.is_active and room != getattr(self.instance, "room", None):
            raise serializers.ValidationError("room_inactive")
        return room


class RoleAssignmentSetupSerializer(SetupSerializer):
    """Who holds which duty, where and when. Only `valid_to` can change afterwards: to end a role
    set it; to resume the role later, create a new assignment. A School admin granting themselves
    principal_board creates a `pending_confirmation` row that grants nothing until a second
    person confirms it (`confirm` action)."""

    IMMUTABLE = (
        "membership",
        "role",
        "school_year",
        "subject_group",
        "school_class",
        "subject",
        "valid_from",
    )

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
            "status",
            "requested_by",
            "confirmed_by",
            "confirmed_at",
        ]
        read_only_fields = ["status", "requested_by", "confirmed_by", "confirmed_at"]

    def validate_membership(self, membership):
        if membership.status != Membership.Status.ACTIVE:
            raise serializers.ValidationError("membership_inactive")
        return membership

    def validate_subject(self, subject):
        if subject is not None and not subject.is_active:
            raise serializers.ValidationError("subject_inactive")
        return subject

    def validate_valid_to(self, valid_to):
        """History stays: an ended period is closed, and a period never reopens."""
        role = self.instance
        if role is None or valid_to == role.valid_to:
            return valid_to
        if valid_to is None:
            raise serializers.ValidationError("valid_to_cannot_be_cleared")
        if role.valid_to is not None and role.valid_to < timezone.localdate():
            raise serializers.ValidationError("period_already_ended")
        if valid_to < role.valid_from:
            raise serializers.ValidationError("valid_to_before_valid_from")
        ends_earlier = role.valid_to is None or valid_to < role.valid_to
        if ends_earlier and role.role == RoleAssignment.Role.SCHOOL_ADMIN:
            in_force = RoleAssignment.objects.in_force().filter(role=role.role)
            if in_force.filter(pk=role.pk).exists() and not (
                in_force.exclude(membership=role.membership_id).exists()
            ):
                raise serializers.ValidationError("last_school_admin")
        return valid_to

    def create(self, validated_data):
        me = self.context["request"].membership
        if (
            validated_data["membership"] == me
            and validated_data["role"] == RoleAssignment.Role.PRINCIPAL_BOARD
        ):
            validated_data |= {
                "status": RoleAssignment.Status.PENDING_CONFIRMATION,
                "requested_by": me,
            }
        return super().create(validated_data)
