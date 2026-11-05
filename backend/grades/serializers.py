from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from schools.models import SchoolClass, Subject, Term

from .models import Gradebook, GradebookColumn, ScoreEntry

MAX_CELLS_PER_SAVE = 2000


class OpenGradebookSerializer(serializers.Serializer):
    """`POST gradebooks/`: which gradebook to open (or find)."""

    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    school_class = serializers.PrimaryKeyRelatedField(queryset=SchoolClass.objects.all())


@extend_schema_field({"type": "number", "nullable": True})
class ScoreValueField(serializers.JSONField):
    """Any JSON value is taken as sent: a cell's value is judged cell by cell (`wrong_form`,
    `too_many_decimals`, `out_of_range`), never by a field error that fails the whole save."""


class CellInputSerializer(serializers.Serializer):
    """One cell to save: a scored subject's `value`, a comment-only subject's `result`, neither
    to clear it. `expected` is the id of the cell's current entry as the client last saw it (null
    for an empty cell)."""

    column = serializers.IntegerField()
    student = serializers.IntegerField()
    value = ScoreValueField(required=False, allow_null=True, default=None)
    result = serializers.ChoiceField(
        choices=ScoreEntry.Result.choices, required=False, allow_null=True, default=None
    )
    expected = serializers.IntegerField(allow_null=True)


class SaveCellsSerializer(serializers.Serializer):
    cells = CellInputSerializer(many=True, allow_empty=False, max_length=MAX_CELLS_PER_SAVE)

    def validate(self, attrs):
        keys = [(cell["column"], cell["student"]) for cell in attrs["cells"]]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError({"request": ["duplicate_cell"]})
        return attrs


class SavedCellSerializer(serializers.Serializer):
    column = serializers.IntegerField()
    student = serializers.IntegerField()
    entry = serializers.IntegerField(allow_null=True)


class SavedCellsSerializer(serializers.Serializer):
    cells = SavedCellSerializer(many=True)


class CurrentEntrySerializer(serializers.Serializer):
    """A cell's current entry, shown beside a conflicting save."""

    entry = serializers.IntegerField()
    value = serializers.DecimalField(
        max_digits=3, decimal_places=1, allow_null=True, coerce_to_string=False
    )
    result = serializers.ChoiceField(choices=ScoreEntry.Result.choices, allow_null=True)
    entered_by_name = serializers.CharField()
    entered_at = serializers.DateTimeField()


class CellErrorSerializer(serializers.Serializer):
    column = serializers.IntegerField()
    student = serializers.IntegerField()
    code = serializers.ChoiceField(
        choices=["conflict", "out_of_range", "too_many_decimals", "wrong_form", "not_enrolled"]
    )
    current = CurrentEntrySerializer(allow_null=True)


class SaveRefusedSerializer(serializers.Serializer):
    """The 400 of a save, by what refused it: `cells` (each failing cell, nothing saved), `request`
    (`unknown_column`, `duplicate_cell`), `gradebook` (`not_draft`) or `constraint` (a rule only
    the database holds). A malformed body is DRF's own field errors under `cells`."""

    cells = CellErrorSerializer(many=True, required=False)
    request = serializers.ListField(child=serializers.CharField(), required=False)
    gradebook = serializers.ListField(child=serializers.CharField(), required=False)
    constraint = serializers.ListField(child=serializers.CharField(), required=False)


class GradebookSerializer(serializers.ModelSerializer):
    """A gradebook in a list."""

    term_name = serializers.CharField(source="term.name")
    subject_name = serializers.CharField(source="subject.name")
    assessment = serializers.ChoiceField(
        choices=Subject.Assessment.choices, source="subject.assessment", read_only=True
    )
    class_name = serializers.CharField(source="school_class.name")

    class Meta:
        model = Gradebook
        fields = [
            "id",
            "school_year",
            "term",
            "term_name",
            "subject",
            "subject_name",
            "assessment",
            "school_class",
            "class_name",
            "status",
            "opened_at",
        ]
        read_only_fields = fields


class ColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradebookColumn
        fields = ["id", "kind", "index", "released_at"]
        read_only_fields = fields


class CellSerializer(serializers.Serializer):
    """A cell with a current entry (an empty cell has none). A cleared cell has an entry with
    neither value nor result."""

    column = serializers.IntegerField()
    entry = serializers.IntegerField()
    value = serializers.DecimalField(
        max_digits=3, decimal_places=1, allow_null=True, coerce_to_string=False
    )
    result = serializers.ChoiceField(choices=ScoreEntry.Result.choices, allow_null=True)
    changed_after_release = serializers.BooleanField()


class RowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    in_class = serializers.BooleanField()
    cells = CellSerializer(many=True)


class GradebookDetailSerializer(GradebookSerializer):
    """The grid: header, columns, and a row per student enrolled in the class during the term."""

    profile_source = serializers.CharField()
    can_enter = serializers.BooleanField()
    columns = ColumnSerializer(many=True)
    students = RowSerializer(many=True)

    class Meta(GradebookSerializer.Meta):
        fields = [
            *GradebookSerializer.Meta.fields,
            "profile_source",
            "can_enter",
            "columns",
            "students",
        ]
        read_only_fields = fields


class StudentNameSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ReleaseRefusedSerializer(serializers.Serializer):
    """The 400 of a release: `column` (`incomplete`, with the enrolled `students` the column still
    lacks a score for, or `already_released`), `gradebook` (`not_draft`) or `constraint`."""

    column = serializers.ListField(child=serializers.CharField(), required=False)
    students = StudentNameSerializer(many=True, required=False)
    gradebook = serializers.ListField(child=serializers.CharField(), required=False)
    constraint = serializers.ListField(child=serializers.CharField(), required=False)


class OpenRefusedSerializer(serializers.Serializer):
    """The 400 of opening a gradebook: `gradebook` (`no_profile_version`, `no_subject_load`),
    `term` (`not_in_class_year`), `constraint`, or a field error of the body."""

    term = serializers.ListField(child=serializers.CharField(), required=False)
    subject = serializers.ListField(child=serializers.CharField(), required=False)
    school_class = serializers.ListField(child=serializers.CharField(), required=False)
    gradebook = serializers.ListField(child=serializers.CharField(), required=False)
    constraint = serializers.ListField(child=serializers.CharField(), required=False)


class HistoryEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    value = serializers.DecimalField(
        max_digits=3, decimal_places=1, allow_null=True, coerce_to_string=False
    )
    result = serializers.ChoiceField(choices=ScoreEntry.Result.choices, allow_null=True)
    entered_by_name = serializers.CharField()
    entered_at = serializers.DateTimeField()


class MyTermSerializer(serializers.Serializer):
    term = serializers.IntegerField()
    term_name = serializers.CharField()
    gradebook = serializers.IntegerField(allow_null=True)
    status = serializers.ChoiceField(choices=Gradebook.Status.choices, allow_null=True)


class MyPairSerializer(serializers.Serializer):
    subject = serializers.IntegerField()
    subject_name = serializers.CharField()
    school_class = serializers.IntegerField()
    class_name = serializers.CharField()
    terms = MyTermSerializer(many=True)
