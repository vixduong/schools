from rest_framework import serializers

from grades.models import GradebookColumn, ScoreEntry
from timetable.models import AttendanceMark, BellPeriod

# Names only: no serializer here reaches an Account (no RLS on it), so no email or phone can leak.


class ChildSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    class_name = serializers.CharField(allow_null=True)  # today's class; null when not enrolled
    left = serializers.BooleanField()


class ChildPeriodSerializer(serializers.Serializer):
    """A period of the child's class on the day, with the child's mark (null when not taken or not
    readable). The mark's note is never returned (free text, Least data)."""

    session = serializers.ChoiceField(choices=BellPeriod.Session.choices)
    number = serializers.IntegerField()
    starts_at = serializers.TimeField()
    ends_at = serializers.TimeField()
    subject_name = serializers.CharField()
    teacher_name = serializers.CharField(allow_null=True)
    room_name = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=AttendanceMark.Status.choices, allow_null=True)


class ChildDaySerializer(serializers.Serializer):
    on = serializers.DateField()  # the School's day the periods are for
    periods = ChildPeriodSerializer(many=True)


class ReleasedCellSerializer(serializers.Serializer):
    """A released column with the child's current entry (value and result null when empty or
    cleared)."""

    kind = serializers.ChoiceField(choices=GradebookColumn.Kind.choices)
    index = serializers.IntegerField()
    value = serializers.DecimalField(
        max_digits=3, decimal_places=1, allow_null=True, coerce_to_string=False
    )
    result = serializers.ChoiceField(choices=ScoreEntry.Result.choices, allow_null=True)
    changed_after_release = serializers.BooleanField()


class ChildGradebookSerializer(serializers.Serializer):
    subject_name = serializers.CharField()
    class_name = serializers.CharField()
    columns = ReleasedCellSerializer(many=True)


class ChildScoresSerializer(serializers.Serializer):
    term = serializers.IntegerField(allow_null=True)  # null: no term in force today
    term_name = serializers.CharField(allow_null=True)
    gradebooks = ChildGradebookSerializer(many=True)
