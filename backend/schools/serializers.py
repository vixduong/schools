import re
from collections.abc import Mapping

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from accounts.invitations import issue_code
from accounts.models import Invitation, InvitationRole, Membership, RoleAssignment
from accounts.serializers import IdentifierField
from permissions.actor import Actor
from permissions.engine import can

from .models import (
    AssessmentProfileVersion,
    Enrollment,
    Grade,
    GuardianLink,
    ImportBatch,
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
    """Who holds which duty, where and when. Only `valid_to` can change afterwards, and the named
    duties of a principal-board member: `can_reopen_gradebooks` and `signs_for_principal` (the
    School names who reopens gradebooks and who signs for the principal), and `title`, which is
    set once while empty and then stays. All three stay empty on every other role. To end a role
    set `valid_to`; to resume the role later, create a new assignment.

    Duties are sensitive: nobody turns on `can_reopen_gradebooks`, `signs_for_principal` or
    `title=principal` on their own row (400 `self_duty_change`); another School admin or
    principal-board member does it. On a row still `pending_confirmation` the duties cannot change
    at all (400 `pending_confirmation`). A School admin granting themselves principal_board
    creates a `pending_confirmation` row that grants nothing until a second person confirms it
    (`confirm` action)."""

    IMMUTABLE = (
        "membership",
        "role",
        "school_year",
        "subject_group",
        "school_class",
        "subject",
        "valid_from",
    )
    DUTY_FIELDS = ("title", "can_reopen_gradebooks", "signs_for_principal")

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
            "title",
            "can_reopen_gradebooks",
            "signs_for_principal",
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

    def validate_title(self, title):
        stored = getattr(self.instance, "title", None)
        if stored is not None and title != stored:
            raise serializers.ValidationError("immutable")
        return title

    def validate(self, attrs):
        row = self.instance
        mine = (attrs["membership"] if row is None else row.membership) == (
            self.context["request"].membership
        )
        principal = RoleAssignment.Title.PRINCIPAL

        def stored(name):
            return getattr(row, name, RoleAssignment._meta.get_field(name).get_default())

        changed = [n for n in self.DUTY_FIELDS if n in attrs and attrs[n] != stored(n)]
        turned_on = [n for n in changed if attrs[n] in (True, principal)]
        if mine and turned_on:
            raise serializers.ValidationError({n: ["self_duty_change"] for n in turned_on})
        if row is not None and row.status == RoleAssignment.Status.PENDING_CONFIRMATION and changed:
            raise serializers.ValidationError({n: ["pending_confirmation"] for n in changed})
        return attrs

    def check_may_end_earlier(self, role, valid_to):
        """Ending (or shortening) a School admin's row must leave admin coverage continuous: some
        other in-force School admin row (active, confirmed, active Membership) must be open-ended
        or last beyond the new `valid_to`. Every in-force School admin row is locked first (in id
        order, so two admins cannot deadlock): two admins ending each other's rows at once
        serialize here, and the second sees the first's committed end and is refused."""
        ensure_school_admin_coverage(role, valid_to)

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


def ensure_school_admin_coverage(role, valid_to):
    """Ending `role` on `valid_to` (an assignment, or a Membership being deactivated) must leave
    School admin coverage continuous; see `check_may_end_earlier`."""
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
    # Shown only to who may `student_profile.view_sensitive` (the student's homeroom teacher, the
    # principal board, the School admin); everyone else gets the keys left out.
    SENSITIVE = ("ministry_student_id", "national_id")

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

    def to_representation(self, student):
        data = super().to_representation(student)
        actor = Actor.of(self.context["request"])
        if not can(actor, "student_profile.view_sensitive", student):
            for name in self.SENSITIVE:
                data.pop(name, None)
        return data

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
        if data.get("national_id"):
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


class MembershipSerializer(serializers.ModelSerializer):
    """A person in this School, by the name on their Account (no identifiers: least data).
    Status changes through `deactivate/` and `reactivate/`."""

    display_name = serializers.CharField(source="account.display_name", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "display_name", "status", "ministry_staff_id"]
        read_only_fields = fields


class InvitationRoleSerializer(serializers.ModelSerializer):
    """A Role Assignment a staff invitation creates on acceptance: the setup API's rules at
    issue time (scope per role and class-in-year are database constraints), checked again at
    acceptance."""

    class Meta:
        model = InvitationRole
        fields = ["role", "school_year", "subject_group", "school_class", "subject", "valid_from"]

    def validate_subject(self, subject):
        return RoleAssignmentSetupSerializer.validate_subject(self, subject)


def may_issue(actor, kind, student, school) -> bool:
    """Staff invitations are `accounts.manage` on the School; guardian and student invitations
    are `guardian_invite.issue` on the student (the School admin, or the student's homeroom
    teacher)."""
    if kind == Invitation.Kind.STAFF:
        return can(actor, "accounts.manage", school)
    return can(actor, "guardian_invite.issue", student)


class InvitationSerializer(SetupSerializer):
    """Who the School expects, and as what. `code` is in the response only when the invitation
    is issued (and in `invitations/print/`, which issues fresh codes). `status` reads `expired`
    for a pending invitation past `expires_at`. `identifier` (VN mobile or email) binds the
    invitation to one sign-in; empty, anyone holding the code may activate it. Payload per
    `kind`: staff `roles`; guardian `student` and `relation`; student `student` (Lower or Upper
    Secondary, without a sign-in yet). Never edited: revoke and issue a new one."""

    identifier = IdentifierField(max_length=254, required=False, allow_null=True, allow_blank=True)
    relation = serializers.ChoiceField(
        GuardianLink.Relation.choices, required=False, allow_null=True
    )
    roles = InvitationRoleSerializer(many=True, required=False)
    student_name = serializers.CharField(source="student.full_name", read_only=True, default=None)
    status = serializers.SerializerMethodField()
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "school",
            "id",
            "kind",
            "identifier",
            "display_name",
            "student",
            "student_name",
            "relation",
            "roles",
            "status",
            "expires_at",
            "created_by",
            "accepted_membership",
            "code",
        ]
        read_only_fields = ["expires_at", "created_by", "accepted_membership"]

    def validate_identifier(self, identifier):
        return identifier or None  # "" never reaches IdentifierField.to_internal_value

    @extend_schema_field(serializers.ChoiceField(choices=[*Invitation.Status.values, "expired"]))
    def get_status(self, invitation):
        return "expired" if invitation.is_expired else invitation.status

    def validate(self, attrs):
        kind, student = attrs["kind"], attrs.get("student")
        if kind != Invitation.Kind.STAFF and student is None:
            raise serializers.ValidationError({"student": ["required"]})
        # Authorise before any check that would tell an outsider about the student.
        request = self.context["request"]
        if not may_issue(Actor.of(request), kind, student, request.school):
            raise PermissionDenied()
        errors = {}
        if kind == Invitation.Kind.STAFF:
            errors |= {n: ["not_for_kind"] for n in ("student", "relation") if attrs.get(n)}
        else:
            if attrs.get("roles"):
                errors["roles"] = ["not_for_kind"]
        if kind == Invitation.Kind.GUARDIAN and not attrs.get("relation"):
            errors["relation"] = ["required"]
        if kind == Invitation.Kind.STUDENT and student is not None:
            if attrs.get("relation"):
                errors["relation"] = ["not_for_kind"]
            if student.membership_id is not None:
                errors["student"] = ["student_has_membership"]
            # As the trigger student_membership_needs_secondary_level checks at acceptance.
            elif not Enrollment.objects.filter(
                student=student,
                school_class__grade__level__kind__in=[
                    Level.Kind.LOWER_SECONDARY,
                    Level.Kind.UPPER_SECONDARY,
                ],
            ).exists():
                errors["student"] = ["student_not_secondary"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        roles = validated_data.pop("roles", [])
        invitation = Invitation(**validated_data)
        code = issue_code(invitation)
        invitation.save()
        InvitationRole.objects.bulk_create(
            InvitationRole(school=invitation.school, invitation=invitation, **role)
            for role in roles
        )
        invitation.code = code
        return invitation


class InvitationPrintSerializer(serializers.Serializer):
    school_class = serializers.PrimaryKeyRelatedField(queryset=SchoolClass.objects.all())


class ImportUploadSerializer(serializers.Serializer):
    """`school_year` is the year whose classes the rows name: required for staff and students."""

    kind = serializers.ChoiceField(ImportBatch.Kind.choices)
    school_year = serializers.PrimaryKeyRelatedField(
        queryset=SchoolYear.objects.all(), required=False, allow_null=True
    )
    file = serializers.FileField()

    def validate(self, attrs):
        if attrs["kind"] != ImportBatch.Kind.GUARDIANS and attrs.get("school_year") is None:
            raise serializers.ValidationError({"school_year": ["required"]})
        return attrs


class ImportBatchSerializer(serializers.ModelSerializer):
    """A previewed (or committed) upload: `counts` of rows by result, every error as
    `{row, column, code}` (`column` is the template's header, null for a whole-row rule), and
    each row's result."""

    counts = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "kind",
            "school_year",
            "status",
            "created_at",
            "uploaded_by",
            "counts",
            "errors",
            "results",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DictField(child=serializers.IntegerField()))
    def get_counts(self, batch):
        counts = {"rows": len(batch.rows), "errors": len({e["row"] for e in batch.errors})}
        for result in batch.results:
            counts[result["result"]] = counts.get(result["result"], 0) + 1
        return counts


class AssessmentProfileVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentProfileVersion
        fields = ["id", "level_kind", "effective_from", "effective_to", "source", "rules"]
        read_only_fields = fields
