from django.db import models, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.permissions import HasMembership
from permissions.actor import Actor
from permissions.engine import can, capabilities
from permissions.matrix import Scope
from schools.models import SchoolClass, SubjectGroup
from schools.views import database_rules

from . import serializers
from .models import Notice, NoticeRecipient
from .services import create_notice
from .tasks import email_notice

Audience = Notice.Audience
MAX_LISTED = 100

# Each audience is tied to one scope of the matrix row "Send notices" (docs/roles.md): the engine
# is asked per audience, never a hand-rolled check.
SEND_SCOPE = {
    Audience.SCHOOL: Scope.SCHOOL,
    Audience.GROUP: Scope.GROUP_SUBJECTS,
    Audience.HOMEROOM_GUARDIANS: Scope.HOMEROOM_CLASS,
    Audience.CLASS: Scope.TEACHING_CLASSES,
}
# The target column an audience names (none for the whole School).
TARGET_COLUMN = {
    Audience.GROUP: "subject_group",
    Audience.HOMEROOM_GUARDIANS: "school_class",
    Audience.CLASS: "school_class",
}
CLASS_AUDIENCE = {
    Scope.HOMEROOM_CLASS: Audience.HOMEROOM_GUARDIANS,
    Scope.TEACHING_CLASSES: Audience.CLASS,
}


def sent_notices():
    """Notices with the counts a sender sees (`recipient_count`, `read_count`)."""
    return Notice.objects.select_related(
        "sender__account", "school_class", "subject_group"
    ).annotate(
        recipient_count=models.Count("noticerecipient"),
        read_count=models.Count(
            "noticerecipient", filter=models.Q(noticerecipient__read_at__isnull=False)
        ),
    )


def received(membership):
    return NoticeRecipient.objects.filter(membership=membership).select_related(
        "notice__sender__account"
    )


class NoticesView(GenericAPIView):
    """Notices. GET: the ones the member received, newest first (at most 100); `?sent=1`: the ones
    they sent, with counts. POST: send one to an audience the member may reach; the recipients
    are fixed now, and the email goes out after the commit."""

    permission_classes = [HasMembership]
    serializer_class = serializers.SendNoticeSerializer

    @extend_schema(
        parameters=[OpenApiParameter("sent", int, description="1: the notices the member sent")],
        responses=PolymorphicProxySerializer(
            component_name="NoticeList",
            serializers=[serializers.ReceivedNoticeSerializer, serializers.SentNoticeSerializer],
            resource_type_field_name=None,
            many=True,
        ),
    )
    def get(self, request):
        if request.query_params.get("sent") == "1":
            notices = sent_notices().filter(sender=request.membership)
            notices = notices.order_by("-sent_at", "-id")[:MAX_LISTED]
            return Response(serializers.SentNoticeSerializer(notices, many=True).data)
        rows = received(request.membership).order_by("-notice__sent_at", "-notice_id")[:MAX_LISTED]
        return Response(serializers.ReceivedNoticeSerializer(rows, many=True).data)

    @extend_schema(
        request=serializers.SendNoticeSerializer,
        responses={
            201: serializers.SentNoticeSerializer,
            400: serializers.SendRefusedSerializer,
        },
    )
    def post(self, request):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        audience = Audience(data["audience"])
        targets = {}
        for column, model in (("school_class", SchoolClass), ("subject_group", SubjectGroup)):
            if data.get(column) is not None:
                # Looked up in this School (RLS), never trusted from the request.
                targets[column] = model.objects.filter(pk=data[column]).first()
                if targets[column] is None:
                    raise ValidationError({column: ["unknown"]})
        needed = TARGET_COLUMN.get(audience)
        if needed is not None and needed not in targets:
            raise ValidationError({needed: ["required"]})
        target = targets[needed] if needed else request.school
        if not can(Actor.of(request), "notices.send", target, scope=SEND_SCOPE[audience]):
            raise PermissionDenied
        with database_rules():
            notice = create_notice(
                school=request.school,
                sender=request.membership,
                audience=audience,
                title=data["title"],
                body=data["body"],
                **targets,
            )
            if notice.recipient_count == 0:
                # Raised, so the notice and its audit row are rolled back with the request.
                raise ValidationError({"recipients": ["none"]})
        # After the commit, so a rolled-back send emails nobody; robust, so a queue that is down
        # does not turn a committed notice into a 500 (a retry would send a second notice).
        school_id, notice_id = request.school.pk, notice.pk
        transaction.on_commit(
            lambda: email_notice.enqueue(school_id=school_id, notice_id=notice_id), robust=True
        )
        return Response(
            serializers.SentNoticeSerializer(sent_notices().get(pk=notice.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class AudiencesView(GenericAPIView):
    """What the member may send to: the `notices.send` entry of `capabilities` with names. Empty
    for a member who may send nothing."""

    permission_classes = [HasMembership]
    serializer_class = serializers.AudienceSerializer

    @extend_schema(responses=serializers.AudienceSerializer(many=True))
    def get(self, request):
        entry = next(
            (c for c in capabilities(Actor.of(request)) if c["action"] == "notices.send"), None
        )
        found = []
        for scope in entry["scopes"] if entry else []:
            if scope["access"] != "write":
                continue
            if scope["kind"] == Scope.SCHOOL:
                found.append({"audience": Audience.SCHOOL})
            elif scope["kind"] == Scope.GROUP_SUBJECTS:
                groups = SubjectGroup.objects.filter(pk__in=scope["subject_groups"])
                found += [
                    {"audience": Audience.GROUP, "subject_group": {"id": g.pk, "name": g.name}}
                    for g in groups.order_by("name", "id")
                ]
            else:
                classes = SchoolClass.objects.filter(pk__in=scope["school_classes"])
                found += [
                    {
                        "audience": CLASS_AUDIENCE[Scope(scope["kind"])],
                        "school_class": {"id": c.pk, "name": c.name},
                    }
                    for c in classes.order_by("name", "id")
                ]
        return Response(serializers.AudienceSerializer(found, many=True).data)


class NoticeReadView(GenericAPIView):
    """The recipient opens a notice: the read mark is set once (a second call answers with the
    first time). A member who is not a recipient finds nothing."""

    permission_classes = [HasMembership]
    serializer_class = serializers.ReceivedNoticeSerializer

    @extend_schema(request=None, responses=serializers.ReceivedNoticeSerializer)
    def post(self, request, pk):
        mine = received(request.membership).filter(notice_id=pk)
        row = mine.first()
        if row is None:
            raise NotFound
        # The row is changed only while the mark is empty, which the set-once trigger also holds.
        NoticeRecipient.objects.filter(pk=row.pk, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return Response(serializers.ReceivedNoticeSerializer(mine.get()).data)
