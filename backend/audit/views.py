from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.fields import DateTimeField, IntegerField
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from accounts.permissions import HasMembership
from permissions.drf import Can

from . import serializers
from .models import AuditEvent, SupportGrant


class NewestFirst(CursorPagination):
    ordering = "-id"
    page_size = 100


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("target_table", str, description="Only this table"),
            OpenApiParameter("target_id", int, description="Only this row (with target_table)"),
            OpenApiParameter("actor_membership", int, description="Only this member's actions"),
            OpenApiParameter("since", str, description="At or after this time (ISO 8601)"),
            OpenApiParameter("until", str, description="Before this time (ISO 8601)"),
        ]
    )
)
class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The School's audit log, newest first (`audit.read`: School admin and principal board, read
    only). Nobody edits or deletes an entry; the database refuses it."""

    permission_classes = [HasMembership, Can("audit.read", read=True)]
    queryset = AuditEvent.objects.all()
    serializer_class = serializers.AuditEventSerializer
    pagination_class = NewestFirst

    def filter_queryset(self, queryset):
        params = self.request.query_params
        if "target_table" in params:
            queryset = queryset.filter(target_table=params["target_table"])
        for name in ("target_id", "actor_membership"):
            if name in params:
                field = "actor_membership_id" if name == "actor_membership" else name
                queryset = queryset.filter(**{field: IntegerField().run_validation(params[name])})
        for name, lookup in (("since", "at__gte"), ("until", "at__lt")):
            if name in params:
                queryset = queryset.filter(**{lookup: DateTimeField().run_validation(params[name])})
        return super().filter_queryset(queryset)


class SupportGrantViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Time-limited, read-only support access for the platform operator
    (`support_access.grant`: School admin and principal board). The operator uses it through
    the `support_session` server command; every grant, revoke, session and command is in the
    audit log."""

    permission_classes = [HasMembership, Can("support_access.grant")]
    queryset = SupportGrant.objects.order_by("-id")
    serializer_class = serializers.SupportGrantSerializer

    def perform_create(self, serializer):
        serializer.save(granted_by=self.request.membership)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """End the grant now; a session in progress stops at its next command."""
        grant = SupportGrant.objects.select_for_update().get(pk=self.get_object().pk)
        if grant.revoked_at is not None or grant.ends_at <= timezone.now():
            raise ValidationError({"status": ["not_in_force"]})
        grant.revoked_at, grant.revoked_by = timezone.now(), request.membership
        grant.save(update_fields=["revoked_at", "revoked_by"])
        return Response(self.get_serializer(grant).data)
