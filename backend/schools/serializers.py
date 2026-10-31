import re
from collections.abc import Mapping

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.models import Membership, RoleAssignment

from .models import (
    AssessmentProfileVersion,
    Enrollment,
    Grade,
    GuardianLink,
    Level,
    Room,
    SchoolClass,
    SchoolYear,
    Student,
    StudentStatusEvent,
    Subject,
    SubjectGroup,
    Term,
    scheduled_change,
    status_as_of,
)


class CurrentSchool:
    """Default for the hidden `school` field: the School of the request. Having `school` among
    the serializer fields also lets DRF build the (school, ...) unique validators."""

    requires_context = True

    def __call__(self, serializer_field):
        return serializer_field.context["request"].school


def _text(value):
    return None if value is None else str(value)


class SetupSerializer(serializers.ModelSerializer):
    """`IMMUTABLE` fields are read-only once the row exists: sending one with a value that differs
    from the stored one answers 400 `{"<field>": ["immutable"]}` (the same value is accepted, so a
    client may PUT the whole row back)."""

    IMMUTABLE: tuple[str, ...] = ()

    school = serializers.HiddenField(default=CurrentSchool())

    def to_internal_value(self, data):
        if self.instance is not None and isinstance(data, Mapping):
            stored = self.to_representation(self.instance)
            changed = {
                name: ["immutable"]
                for name in self.IMMUTABLE
                if name in data and _text(data[name]) != _text(stored[name])
            }
            if changed:
                raise serializers.ValidationError(changed)
        return super().to_internal_value(data)

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


class PeriodSerializer(SetupSerializer):
    """A row with a period `valid_from`..`valid_to` (inclusive, open-ended when null). History
    stays: an ended period is closed, and a period never reopens or starts earlier (the one
    exception is cancelling a leave scheduled in the future, `students/{id}/leave/cancel/`). A
    subclass refuses an ending by overriding `check_may_end_earlier`."""

    def check_may_end_earlier(self, row, valid_to):
        pass

    def validate_valid_to(self, valid_to):
        row = self.instance
        if row is None or valid_to == row.valid_to:
            return valid_to
        if valid_to is None:
            raise serializers.ValidationError("valid_to_cannot_be_cleared")
        if row.valid_to is not None and row.valid_to < timezone.localdate():
            raise serializers.ValidationError("period_already_ended")
        if valid_to < row.valid_from:
            raise serializers.ValidationError("valid_to_before_valid_from")
        if row.valid_to is None or valid_to < row.valid_to:
            self.check_may_end_earlier(row, valid_to)
        return valid_to


class RoleAssignmentSetupSerializer(PeriodSerializer):
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
        return _not_a_student(membership)

    def validate_subject(self, subject):
        if subject is not None and not subject.is_active:
            raise serializers.ValidationError("subject_inactive")
        return subject

    def check_may_end_earlier(self, role, valid_to):
        """Ending (or shortening) a School admin's row must leave admin coverage continuous: some
        other in-force School admin row (active, confirmed, active Membership) must be open-ended
        or last beyond the new `valid_to`. Every in-force School admin row is locked first (in id
        order, so two admins cannot deadlock): two admins ending each other's rows at once
        serialize here, and the second sees the first's committed end and is refused."""
        if role.role != RoleAssignment.Role.SCHOOL_ADMIN:
            return
        in_force = list(
            RoleAssignment.objects.in_force()
            .filter(role=role.role)
            .select_for_update(of=("self",))
            .order_by("pk")
        )
        covered = any(
            r.membership_id != role.membership_id and (r.valid_to is None or r.valid_to > valid_to)
            for r in in_force
        )
        if any(r.pk == role.pk for r in in_force) and not covered:
            raise serializers.ValidationError("last_school_admin")

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


def _active_membership(membership):
    if membership is not None and membership.status != Membership.Status.ACTIVE:
        raise serializers.ValidationError("membership_inactive")
    return membership


def _not_a_student(membership):
    """A student's sign-in never holds a staff role or a Guardian link (a staff member may be a
    Guardian)."""
    if Student.objects.filter(membership=membership).exists():
        raise serializers.ValidationError("membership_is_student")
    return membership


def _id_or_none(value):
    """An identifier left blank is NULL, so the per-School uniques never collide on blanks."""
    return (value or "").strip() or None


class ScheduledChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Student.Status.choices)
    on = serializers.DateField()


class StudentSerializer(SetupSerializer):
    """`status` is the status today and `scheduled_change` the next change after today (or null),
    both derived from the status events: neither is writable (sending a different `status` on
    update answers 400 `immutable`); events come through `students/{id}/status-events/` and
    `students/{id}/leave/`. `membership` (the student's sign-in) is for Lower and Upper Secondary
    students and needs an Enrollment in such a class first; it is never a staff or Guardian
    Membership, nor the requester's own."""

    IMMUTABLE = ("status",)

    status = serializers.SerializerMethodField()
    scheduled_change = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "school",
            "id",
            "full_name",
            "date_of_birth",
            "gender",
            "ministry_student_id",
            "national_id",
            "membership",
            "status",
            "scheduled_change",
        ]

    @extend_schema_field(serializers.ChoiceField(choices=Student.Status.choices))
    def get_status(self, student):
        return status_as_of(student.studentstatusevent_set.all(), timezone.localdate())

    @extend_schema_field(ScheduledChangeSerializer(allow_null=True))
    def get_scheduled_change(self, student):
        return scheduled_change(student.studentstatusevent_set.all(), timezone.localdate())

    def validate_ministry_student_id(self, value):
        return _id_or_none(value)

    def validate_national_id(self, value):
        value = _id_or_none(value)
        if value is not None and not re.fullmatch(r"[0-9]{12}", value):
            raise serializers.ValidationError("invalid_national_id")
        return value

    def validate_membership(self, membership):
        membership = _active_membership(membership)
        if membership is None:
            return None
        if membership == self.context["request"].membership:
            raise serializers.ValidationError("membership_is_requester")
        if RoleAssignment.objects.filter(membership=membership).exists():
            raise serializers.ValidationError("membership_has_role_assignment")
        if GuardianLink.objects.filter(membership=membership).exists():
            raise serializers.ValidationError("membership_has_guardian_link")
        return membership


class StudentListSerializer(StudentSerializer):
    """The list hides all but the last 3 digits of `national_id`; the full value is only on
    retrieve of one student."""

    def to_representation(self, student):
        data = super().to_representation(student)
        if data["national_id"]:
            data["national_id"] = "*" * (len(data["national_id"]) - 3) + data["national_id"][-3:]
        return data


class StudentStatusEventSerializer(SetupSerializer):
    """`student` and `recorded_by` come from the URL and the request, never from the body. Only
    `studying` (a return, dated today or later) is recorded here; leaving goes through
    `students/{id}/leave/`, which ends the enrollment in the same transaction."""

    class Meta:
        model = StudentStatusEvent
        fields = ["school", "id", "student", "status", "on", "reason", "recorded_by"]
        read_only_fields = ["student", "recorded_by"]

    def validate_status(self, status):
        if status != Student.Status.STUDYING:
            raise serializers.ValidationError("use_leave")
        return status


class EnrollmentSerializer(PeriodSerializer):
    """A student's period in a class. Student, year, start and `reason_started` never change;
    `valid_to` (with `reason_ended`) only ends the period, never clears it, and the only reason
    accepted here is `year_end`: a class change goes through `enrollments/{id}/move/` and a
    leave through `students/{id}/leave/`, so the history and the student's status stay
    consistent. The class changes in place only for a period that is open and has not started
    yet; `reason_ended` changes only in the request that sets `valid_to`. Only a student who is
    studying on the first day can start a period (a student who left and returns first gets a
    `studying` status event, then a `return` period)."""

    IMMUTABLE = ("student", "school_year", "valid_from", "reason_started")

    class Meta:
        model = Enrollment
        fields = [
            "school",
            "id",
            "student",
            "school_year",
            "school_class",
            "valid_from",
            "valid_to",
            "reason_started",
            "reason_ended",
        ]

    def validate_reason_ended(self, reason):
        kept = self.instance is not None and reason == self.instance.reason_ended
        if reason not in (None, Enrollment.ReasonEnded.YEAR_END) and not kept:
            raise serializers.ValidationError("only_year_end")
        return reason

    def validate(self, attrs):
        row = self.instance
        if row is None:
            events = attrs["student"].studentstatusevent_set.all()
            if status_as_of(events, attrs["valid_from"]) != Student.Status.STUDYING:
                raise serializers.ValidationError({"student": ["student_not_studying"]})
        valid_to = attrs.get("valid_to", row.valid_to if row else None)
        reason = attrs.get("reason_ended", row.reason_ended if row else None)
        if valid_to is not None and reason is None:
            raise serializers.ValidationError({"reason_ended": ["required_with_valid_to"]})
        if valid_to is None and reason is not None:
            raise serializers.ValidationError({"valid_to": ["required_with_reason_ended"]})
        if row is not None:
            moved = "school_class" in attrs and attrs["school_class"].pk != row.school_class_id
            if moved and (row.valid_to is not None or row.valid_from < timezone.localdate()):
                raise serializers.ValidationError({"school_class": ["use_move"]})
            if reason != row.reason_ended and valid_to == row.valid_to:
                raise serializers.ValidationError({"reason_ended": ["set_with_valid_to"]})
        return attrs


class EnrollmentMoveSerializer(serializers.Serializer):
    """Move a student to another class of the same year from `on` (the first day there)."""

    school_class = serializers.PrimaryKeyRelatedField(queryset=SchoolClass.objects.all())
    on = serializers.DateField()


class LeaveSerializer(serializers.Serializer):
    """`on` is the student's last day at this School; a future date schedules the leave.
    `destination` (free text) is required for a transfer out."""

    reason = serializers.ChoiceField(
        choices=[
            Enrollment.ReasonEnded.TRANSFER_OUT,
            Enrollment.ReasonEnded.DROPPED_OUT,
            Enrollment.ReasonEnded.GRADUATED,
        ]
    )
    on = serializers.DateField()
    destination = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["reason"] == Enrollment.ReasonEnded.TRANSFER_OUT and not attrs.get("destination"):
            raise serializers.ValidationError({"destination": ["required"]})
        return attrs


class GuardianLinkSerializer(PeriodSerializer):
    """A Guardian's link to a student. End it with `valid_to`; to link again later, create a new
    one. Never deleted. The relation can be corrected until the link has ended. A student's own
    sign-in is no Guardian."""

    IMMUTABLE = ("membership", "student", "valid_from")

    class Meta:
        model = GuardianLink
        fields = [
            "school",
            "id",
            "membership",
            "student",
            "relation",
            "valid_from",
            "valid_to",
        ]

    def validate_membership(self, membership):
        return _not_a_student(_active_membership(membership))

    def validate(self, attrs):
        row = self.instance
        ended = row is not None and row.valid_to is not None and row.valid_to < timezone.localdate()
        if ended and attrs.get("relation", row.relation) != row.relation:
            raise serializers.ValidationError({"relation": ["period_already_ended"]})
        return attrs


class AssessmentProfileVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentProfileVersion
        fields = ["id", "level_kind", "effective_from", "effective_to", "source", "rules"]
        read_only_fields = fields
