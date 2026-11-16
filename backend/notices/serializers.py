from rest_framework import serializers

from .models import MAX_BODY_LENGTH, Notice

MAX_TITLE_LENGTH = 200
MAX_ID = 2**63 - 1
# One code per way a field is refused (the API's error vocabulary, the SPA's message table).
REQUIRED = {"required": "required", "blank": "required", "null": "required"}
UNKNOWN_ID = {"invalid": "unknown", "min_value": "unknown", "max_value": "unknown"}


class SendNoticeSerializer(serializers.Serializer):
    """`POST notices/`. The class or group is looked up by the view, which also decides who may
    send to the audience."""

    audience = serializers.CharField(allow_blank=True, error_messages=REQUIRED)
    school_class = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=MAX_ID, error_messages=UNKNOWN_ID
    )
    subject_group = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=MAX_ID, error_messages=UNKNOWN_ID
    )
    title = serializers.CharField(
        max_length=MAX_TITLE_LENGTH, error_messages={**REQUIRED, "max_length": "too_long"}
    )
    body = serializers.CharField(
        max_length=MAX_BODY_LENGTH, error_messages={**REQUIRED, "max_length": "too_long"}
    )

    def validate_audience(self, audience: str) -> str:
        if audience not in Notice.Audience.values:
            raise serializers.ValidationError("unknown")
        return audience

    def validate_title(self, title: str) -> str:
        if "\n" in title or "\r" in title:  # the title is the mail subject
            raise serializers.ValidationError("single_line")
        return title


class SendRefusedSerializer(serializers.Serializer):
    """The 400 of sending: a field's codes, `recipients` (`none`), or `constraint`."""

    audience = serializers.ListField(child=serializers.CharField(), required=False)
    school_class = serializers.ListField(child=serializers.CharField(), required=False)
    subject_group = serializers.ListField(child=serializers.CharField(), required=False)
    title = serializers.ListField(child=serializers.CharField(), required=False)
    body = serializers.ListField(child=serializers.CharField(), required=False)
    recipients = serializers.ListField(child=serializers.CharField(), required=False)
    constraint = serializers.ListField(child=serializers.CharField(), required=False)


class NamedSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class AudienceSerializer(serializers.Serializer):
    """What the member may send to: one entry per audience and target."""

    audience = serializers.ChoiceField(choices=Notice.Audience.choices)
    school_class = NamedSerializer(required=False)
    subject_group = NamedSerializer(required=False)


class ReceivedNoticeSerializer(serializers.Serializer):
    """A notice as its recipient reads it (the view gives a `NoticeRecipient`)."""

    id = serializers.IntegerField(source="notice_id")
    title = serializers.CharField(source="notice.title")
    body = serializers.CharField(source="notice.body")
    sent_at = serializers.DateTimeField(source="notice.sent_at")
    sender_name = serializers.CharField(source="notice.sender.account.display_name")
    audience = serializers.ChoiceField(source="notice.audience", choices=Notice.Audience.choices)
    read_at = serializers.DateTimeField(allow_null=True)


class SentNoticeSerializer(serializers.ModelSerializer):
    """A notice as its sender sees it: counts of recipients and read marks, never who read. The
    view annotates `recipient_count` and `read_count`."""

    sender_name = serializers.CharField(source="sender.account.display_name")
    school_class_name = serializers.CharField(
        source="school_class.name", default=None, allow_null=True
    )
    subject_group_name = serializers.CharField(
        source="subject_group.name", default=None, allow_null=True
    )
    recipient_count = serializers.IntegerField()
    read_count = serializers.IntegerField()

    class Meta:
        model = Notice
        fields = [
            "id",
            "title",
            "body",
            "sent_at",
            "sender_name",
            "audience",
            "school_class_name",
            "subject_group_name",
            "recipient_count",
            "read_count",
        ]
        read_only_fields = fields
