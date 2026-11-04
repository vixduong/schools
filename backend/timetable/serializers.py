from datetime import date

from django.utils import timezone
from rest_framework import serializers

from accounts.models import Membership
from schools.models import Room, SchoolClass, Subject
from schools.serializers import setup_serializer

from .models import BellPeriod, TimetableEntry

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


class MyPeriodSerializer(serializers.ModelSerializer):
    """A period of the signed-in teacher's day: times, class, subject and room by name."""

    session = serializers.CharField(source="bell_period.session")
    number = serializers.IntegerField(source="bell_period.number")
    starts_at = serializers.TimeField(source="bell_period.starts_at")
    ends_at = serializers.TimeField(source="bell_period.ends_at")
    class_name = serializers.CharField(source="school_class.name")
    subject_name = serializers.CharField(source="subject.name")
    room_name = serializers.CharField(source="room.name", default=None)

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
        ]
        read_only_fields = fields
