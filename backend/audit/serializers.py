from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from schools.serializers import CurrentSchool

from .models import AuditEvent, SupportGrant

MAX_HOURS = 72


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "at",
            "actor",
            "actor_membership",
            "action",
            "target_table",
            "target_id",
            "details",
        ]
        read_only_fields = fields


class SupportGrantSerializer(serializers.ModelSerializer):
    """Let the platform operator in, read only, from now for `hours` (1 to 72). Never edited:
    `revoke/` ends it early."""

    school = serializers.HiddenField(default=CurrentSchool())
    hours = serializers.IntegerField(min_value=1, max_value=MAX_HOURS, write_only=True)
    in_force = serializers.SerializerMethodField()

    class Meta:
        model = SupportGrant
        fields = [
            "school",
            "id",
            "reason",
            "hours",
            "starts_at",
            "ends_at",
            "in_force",
            "granted_by",
            "revoked_at",
            "revoked_by",
        ]
        read_only_fields = ["starts_at", "ends_at", "granted_by", "revoked_at", "revoked_by"]

    def get_in_force(self, grant) -> bool:
        now = timezone.now()
        return grant.revoked_at is None and grant.starts_at <= now < grant.ends_at

    def create(self, validated_data):
        now = timezone.now()
        hours = validated_data.pop("hours")
        return super().create(
            validated_data | {"starts_at": now, "ends_at": now + timedelta(hours=hours)}
        )
