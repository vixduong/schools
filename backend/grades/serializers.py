from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from schools.models import SchoolClass, Subject, Term

from .models import CarriedResult, Gradebook, GradebookColumn, GradebookStep, ScoreEntry

MAX_CELLS_PER_SAVE = 2000
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


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


class ReviewItemSerializer(GradebookSerializer):
    """A gradebook in the reviewer's queue (`?to_review=1`) with its latest submit. The plain list
    leaves both fields out."""

    submitted_by_name = serializers.CharField(required=False)
    submitted_at = serializers.DateTimeField(required=False)

    class Meta(GradebookSerializer.Meta):
        fields = [*GradebookSerializer.Meta.fields, "submitted_by_name", "submitted_at"]
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


class CarriedSerializer(serializers.Serializer):
    """The current carried result of one kind and index (a cleared one is left out)."""

    kind = serializers.ChoiceField(choices=CarriedResult.Kind.choices)
    index = serializers.IntegerField()
    value = serializers.DecimalField(
        max_digits=3, decimal_places=1, allow_null=True, coerce_to_string=False
    )
    result = serializers.ChoiceField(choices=ScoreEntry.Result.choices, allow_null=True)


class ArrivalSerializer(serializers.Serializer):
    """A student who arrived during the term: the day, and, once recorded, the source School and
    the transfer document's name (null before)."""

    arrived_on = serializers.DateField()
    source_school = serializers.CharField(allow_null=True)
    document_name = serializers.CharField(allow_null=True)
    recorded_at = serializers.DateTimeField(allow_null=True)


class MissingColumnSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=GradebookColumn.Kind.choices)
    index = serializers.IntegerField()


class AverageSerializer(serializers.Serializer):
    """A semester or year average (`grades/averages.py`, never stored): `value` for a scored
    subject, `result` for a comment-only one, each only when `state` is `final` or
    `provisional`; `missing` lists the empty columns; `carried` says a carried result was used;
    `reason` explains `unavailable` (`rules`, `terms`) or a year's `no_previous_average`."""

    value = serializers.DecimalField(
        max_digits=3, decimal_places=1, allow_null=True, coerce_to_string=False
    )
    result = serializers.ChoiceField(choices=ScoreEntry.Result.choices, allow_null=True)
    state = serializers.ChoiceField(
        choices=["final", "provisional", "missing", "left", "split", "unavailable"]
    )
    missing = MissingColumnSerializer(many=True)
    carried = serializers.BooleanField()
    reason = serializers.ChoiceField(
        choices=["rules", "terms", "no_previous_average"], allow_null=True
    )


class RowAveragesSerializer(serializers.Serializer):
    """`year` is null outside a semester 2 gradebook."""

    semester = AverageSerializer()
    year = AverageSerializer(allow_null=True)


class RowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    in_class = serializers.BooleanField()
    left_on = serializers.DateField(allow_null=True)
    can_carry = serializers.BooleanField()
    arrival = ArrivalSerializer(allow_null=True)
    carried = CarriedSerializer(many=True)
    cells = CellSerializer(many=True)
    averages = RowAveragesSerializer()


class StepSerializer(serializers.Serializer):
    """A step of the workflow, oldest first in the detail. `comment` is a return's comment or a
    reopen's reason (blank for the other steps)."""

    action = serializers.ChoiceField(choices=GradebookStep.Action.choices)
    by_name = serializers.CharField()
    at = serializers.DateTimeField()
    comment = serializers.CharField(allow_blank=True)


class GradebookDetailSerializer(GradebookSerializer):
    """The grid: header, columns, and a row per student enrolled in the class during the term;
    the workflow's `steps`, the `return_comment` of a draft whose latest step is a return, and
    `can`, the steps this member may take now."""

    profile_source = serializers.CharField()
    can_enter = serializers.BooleanField()
    steps = StepSerializer(many=True)
    return_comment = serializers.CharField(allow_null=True)
    can = serializers.ListField(child=serializers.ChoiceField(choices=GradebookStep.Action.choices))
    columns = ColumnSerializer(many=True)
    students = RowSerializer(many=True)

    class Meta(GradebookSerializer.Meta):
        fields = [
            *GradebookSerializer.Meta.fields,
            "profile_source",
            "can_enter",
            "steps",
            "return_comment",
            "can",
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


def required_text(max_length=500):
    """A comment or reason: absent, null or blank answers `required`."""
    return serializers.CharField(
        max_length=max_length,
        error_messages={
            "required": "required",
            "null": "required",
            "blank": "required",
            "max_length": "too_long",
        },
    )


class ReturnSerializer(serializers.Serializer):
    """`POST gradebooks/{id}/return/`."""

    comment = required_text()


class ReopenSerializer(serializers.Serializer):
    """`POST gradebooks/{id}/reopen/`: the reason is kept as the step's comment."""

    reason = required_text()


class EmptyCellSerializer(serializers.Serializer):
    column = serializers.IntegerField()
    student = serializers.IntegerField()
    code = serializers.ChoiceField(choices=["incomplete"])


class StepRefusedSerializer(serializers.Serializer):
    """The 400 of a step: `status` (`wrong_state`, `own_submission`), `cells` (submit or approve:
    each empty cell of a student still in the class), `comment` / `reason` (`required`, `too_long`),
    `constraint` (a rule only the database holds)."""

    status = serializers.ListField(child=serializers.CharField(), required=False)
    cells = EmptyCellSerializer(many=True, required=False)
    comment = serializers.ListField(child=serializers.CharField(), required=False)
    reason = serializers.ListField(child=serializers.CharField(), required=False)
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
    returned = serializers.BooleanField()  # the latest step is a return (a comment to answer)


class MyPairSerializer(serializers.Serializer):
    subject = serializers.IntegerField()
    subject_name = serializers.CharField()
    school_class = serializers.IntegerField()
    class_name = serializers.CharField()
    terms = MyTermSerializer(many=True)


class TransferInputSerializer(serializers.Serializer):
    """`POST gradebooks/{id}/students/{student}/transfer/` (multipart). The file's type is judged by
    its first bytes in the view, its size by the request's length before it is read."""

    source_school = serializers.CharField(
        max_length=200,
        error_messages={
            "required": "required",
            "null": "required",
            "blank": "required",
            "max_length": "too_long",
        },
    )
    document = serializers.FileField(
        error_messages={"required": "required", "null": "required", "empty": "required"}
    )


class CarriedInputSerializer(serializers.Serializer):
    """One carried result to save: a scored subject's `value`, a comment-only subject's `result`,
    neither to clear it."""

    kind = serializers.ChoiceField(choices=CarriedResult.Kind.choices)
    index = serializers.IntegerField(min_value=1)
    value = ScoreValueField(required=False, allow_null=True, default=None)
    result = serializers.ChoiceField(
        choices=ScoreEntry.Result.choices, required=False, allow_null=True, default=None
    )


class SaveCarriedSerializer(serializers.Serializer):
    results = CarriedInputSerializer(many=True, allow_empty=False, max_length=100)

    def validate(self, attrs):
        keys = [(r["kind"], r["index"]) for r in attrs["results"]]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError({"results": ["duplicate"]})
        return attrs


class CarriedErrorSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=CarriedResult.Kind.choices)
    index = serializers.IntegerField()
    code = serializers.ChoiceField(
        choices=["out_of_range", "too_many_decimals", "wrong_form", "unknown_column"]
    )


class TransferRefusedSerializer(serializers.Serializer):
    """The 400 of `transfer/` and `carried/`: `student` (`not_arrived`), `source_school`,
    `document` (`required`, `too_long`, `too_large`, `unsupported_type`), `results` (each failing
    result, nothing saved; or `duplicate`), `gradebook` (`not_draft`) or `constraint`."""

    student = serializers.ListField(child=serializers.CharField(), required=False)
    source_school = serializers.ListField(child=serializers.CharField(), required=False)
    document = serializers.ListField(child=serializers.CharField(), required=False)
    results = CarriedErrorSerializer(many=True, required=False)
    gradebook = serializers.ListField(child=serializers.CharField(), required=False)
    constraint = serializers.ListField(child=serializers.CharField(), required=False)
