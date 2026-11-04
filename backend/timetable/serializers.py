from datetime import date

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.models import Membership
from schools.models import Room, SchoolClass, Subject
from schools.serializers import setup_serializer

from .models import AttendanceMark, BellPeriod, LeaveRequest, TimetableEntry

MAX_LEAVE_DAYS = 30  # `leaverequest_at_most_30_days`

# Which session a bell period belongs to, and its number, never change (a timetable points at it).
BellPeriodSerializer = setup_serializer(
    BellPeriod,
    "school_year",
    "session",
    "number",
    "starts_at",
    "ends_at",
    immutable=("school_year", "session", "number"),
)


class TimetableEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TimetableEntry
        fields = [
            "id",
            "school_year",
            "school_class",
            "weekday",
            "bell_period",
            "subject",
            "teacher",
            "room",
            "valid_from",
            "valid_to",
        ]
        read_only_fields = fields


class TimetableSlotSerializer(serializers.Serializer):
    """One cell of the week the admin saves for a class."""

    weekday = serializers.IntegerField(min_value=1, max_value=7)
    bell_period = serializers.PrimaryKeyRelatedField(queryset=BellPeriod.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    teacher = serializers.PrimaryKeyRelatedField(queryset=Membership.objects.all())
    room = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(), required=False, allow_null=True, default=None
    )


class ReplaceTimetableSerializer(serializers.Serializer):
    """`POST classes/{id}/timetable/`: the class's week, applied from `valid_from` (after today,
    inside the class's year). The class comes from the URL, not from the body."""

    valid_from = serializers.DateField()
    entries = TimetableSlotSerializer(many=True)

    def validate_valid_from(self, valid_from: date) -> date:
        if valid_from <= timezone.localdate():
            raise serializers.ValidationError("not_after_today")
        return valid_from

    def validate(self, attrs):
        klass: SchoolClass = self.context["school_class"]
        year = klass.school_year
        if not year.starts_on <= attrs["valid_from"] <= year.ends_on:
            raise serializers.ValidationError({"valid_from": ["outside_school_year"]})
        for slot in attrs["entries"]:
            if slot["bell_period"].school_year_id != year.pk:
                raise serializers.ValidationError({"entries": ["bell_period_of_another_year"]})
        return attrs


class AttendanceResultSerializer(serializers.Serializer):
    """What a taken period shows on the teacher's home."""

    absent = serializers.IntegerField()
    late = serializers.IntegerField()


class MyPeriodSerializer(serializers.ModelSerializer):
    """A period of the signed-in teacher's day: times, class, subject and room by name."""

    session = serializers.CharField(source="bell_period.session")
    number = serializers.IntegerField(source="bell_period.number")
    starts_at = serializers.TimeField(source="bell_period.starts_at")
    ends_at = serializers.TimeField(source="bell_period.ends_at")
    class_name = serializers.CharField(source="school_class.name")
    subject_name = serializers.CharField(source="subject.name")
    room_name = serializers.CharField(source="room.name", default=None)
    attendance = serializers.SerializerMethodField()

    class Meta:
        model = TimetableEntry
        fields = [
            "id",
            "session",
            "number",
            "starts_at",
            "ends_at",
            "school_class",
            "class_name",
            "subject",
            "subject_name",
            "room",
            "room_name",
            "attendance",
        ]
        read_only_fields = fields

    @extend_schema_field(AttendanceResultSerializer(allow_null=True))
    def get_attendance(self, entry):
        """Null while the period has no marks on the day (the view annotates the counts)."""
        if not entry.marks:
            return None
        return {"absent": entry.absent, "late": entry.late}


class MarkSerializer(serializers.Serializer):
    status = serializers.ChoiceField(AttendanceMark.Status.choices)
    note = serializers.CharField(max_length=200, allow_blank=True)


class SheetLeaveSerializer(serializers.Serializer):
    """The approved leave request covering the sheet's day (no reason: the reader teaches or leads
    the class, and needs only to know the Guardian asked)."""

    id = serializers.IntegerField()
    from_on = serializers.DateField()
    to_on = serializers.DateField()


class SheetStudentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    mark = MarkSerializer(allow_null=True)
    leave = SheetLeaveSerializer(allow_null=True)


class SheetSerializer(serializers.Serializer):
    """A held period on a date and its class list, each student with their mark or null."""

    entry = serializers.IntegerField()
    on = serializers.DateField()
    session = serializers.CharField()
    number = serializers.IntegerField()
    starts_at = serializers.TimeField()
    ends_at = serializers.TimeField()
    school_class = serializers.IntegerField()
    class_name = serializers.CharField()
    subject = serializers.IntegerField()
    subject_name = serializers.CharField()
    room_name = serializers.CharField(allow_null=True)
    can_take = serializers.BooleanField()
    students = SheetStudentSerializer(many=True)


class MarkInputSerializer(MarkSerializer):
    student = serializers.IntegerField()
    note = serializers.CharField(max_length=200, allow_blank=True, default="")


class SaveSheetSerializer(serializers.Serializer):
    """`PUT attendance/{entry}/{on}/`: a mark for every student enrolled that day, no more."""

    marks = MarkInputSerializer(many=True)


class AbsenceSerializer(serializers.Serializer):
    """A late or absent mark in the class overview: the day and the period it was taken in."""

    on = serializers.DateField()
    session = serializers.CharField()
    number = serializers.IntegerField()
    subject_name = serializers.CharField()
    status = serializers.ChoiceField(AttendanceMark.Status.choices)


class OverviewStudentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    marks = AbsenceSerializer(many=True)


class HeldPeriodSerializer(serializers.Serializer):
    """A period the class held on a day, and whether its sheet was taken."""

    on = serializers.DateField()
    session = serializers.CharField()
    number = serializers.IntegerField()
    subject_name = serializers.CharField()
    taken = serializers.BooleanField()


class OverviewSerializer(serializers.Serializer):
    class_name = serializers.CharField()
    students = OverviewStudentSerializer(many=True)
    periods = HeldPeriodSerializer(many=True)


class LeaveRequestSerializer(serializers.ModelSerializer):
    """A leave request with the names a ticket shows. The view sets `class_name` (the student's
    class on `from_on`) on each object."""

    student_name = serializers.CharField(source="student.full_name")
    class_name = serializers.CharField(allow_null=True)
    sent_by_name = serializers.CharField(source="sent_by.account.display_name")
    decided_by_name = serializers.CharField(
        source="decided_by.account.display_name", default=None, allow_null=True
    )

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "student",
            "student_name",
            "class_name",
            "sent_by",
            "sent_by_name",
            "from_on",
            "to_on",
            "reason",
            "status",
            "sent_at",
            "decided_by",
            "decided_by_name",
            "decided_at",
            "decision_comment",
        ]
        read_only_fields = fields


class SendLeaveRequestSerializer(serializers.Serializer):
    """`POST leave-requests/`: the days are whole days from today (the student is checked by the
    view, which authorised on them)."""

    student = serializers.IntegerField()
    from_on = serializers.DateField()
    to_on = serializers.DateField()
    reason = serializers.CharField(max_length=500)

    def validate_from_on(self, from_on: date) -> date:
        if from_on < timezone.localdate():
            raise serializers.ValidationError("in_the_past")
        return from_on

    def validate(self, attrs):
        if attrs["to_on"] < attrs["from_on"]:
            raise serializers.ValidationError({"to_on": ["before_from_on"]})
        if (attrs["to_on"] - attrs["from_on"]).days >= MAX_LEAVE_DAYS:
            raise serializers.ValidationError({"to_on": ["range_too_long"]})
        return attrs


class DecideLeaveRequestSerializer(serializers.Serializer):
    """`.../approve/`: the comment is optional."""

    comment = serializers.CharField(max_length=500, allow_blank=True, default="")


class DeclineLeaveRequestSerializer(DecideLeaveRequestSerializer):
    """`.../decline/`: the comment says why, and is required."""

    comment = serializers.CharField(max_length=500)


class LeaveChildSerializer(serializers.Serializer):
    """A student the member may send a leave request for (the Guardian's child picker)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    class_name = serializers.CharField(allow_null=True)
