from django.db import IntegrityError, transaction
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError

from accounts.models import RoleAssignment
from accounts.permissions import HasMembership, IsSchoolAdmin

from . import serializers
from .models import Grade, Level, Room, SchoolClass, SchoolYear, Subject, SubjectGroup, Term


class SetupViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """School admin only. No DELETE: years, classes and role assignments are ended or kept,
    rooms and subjects are deactivated (history instead of deletes). Querysets need no School
    filter: RLS shows only the request's School."""

    permission_classes = [HasMembership, IsSchoolAdmin]

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    def _save(self, serializer):
        """A rule only the database can check (overlap, term inside year, grade range, role
        scope, same-School references) answers 400 naming the constraint, not 500."""
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as error:
            name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            raise ValidationError({"constraint": [name or "unknown"]}) from error


class SchoolYearViewSet(SetupViewSet):
    queryset = SchoolYear.objects.order_by("starts_on", "id")
    serializer_class = serializers.SchoolYearSerializer


class TermViewSet(SetupViewSet):
    queryset = Term.objects.order_by("starts_on", "id")
    serializer_class = serializers.TermSerializer


class LevelViewSet(SetupViewSet):
    queryset = Level.objects.order_by("id")
    serializer_class = serializers.LevelSerializer


class GradeViewSet(SetupViewSet):
    queryset = Grade.objects.order_by("number")
    serializer_class = serializers.GradeSerializer


class SubjectGroupViewSet(SetupViewSet):
    queryset = SubjectGroup.objects.order_by("name", "id")
    serializer_class = serializers.SubjectGroupSerializer


class SubjectViewSet(SetupViewSet):
    queryset = Subject.objects.order_by("code")
    serializer_class = serializers.SubjectSerializer


class RoomViewSet(SetupViewSet):
    queryset = Room.objects.order_by("name", "id")
    serializer_class = serializers.RoomSerializer


class SchoolClassViewSet(SetupViewSet):
    queryset = SchoolClass.objects.order_by("school_year_id", "name")
    serializer_class = serializers.SchoolClassSerializer


class RoleAssignmentViewSet(SetupViewSet):
    queryset = RoleAssignment.objects.order_by("id")
    serializer_class = serializers.RoleAssignmentSetupSerializer
