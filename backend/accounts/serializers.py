import re

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import serializers

from permissions.engine import capabilities
from tenancy.models import School

from .invitations import code_digest
from .models import (
    PHONE_PATTERN,
    Account,
    Invitation,
    Membership,
    RoleAssignment,
    normalize_email,
    normalize_phone,
)

# Hashed once so a request for an unknown identifier costs as much as a wrong password.
_DUMMY_HASH = make_password("dummy")


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        """Wrong identifier, wrong password, inactive Account and no active Membership in this
        School all give the same error, so a response never says which Schools an Account is in."""
        invalid = serializers.ValidationError("Invalid credentials.", code="invalid_credentials")
        try:
            account = Account.objects.get_by_identifier(attrs["identifier"])
        except Account.DoesNotExist:
            check_password(attrs["password"], _DUMMY_HASH)
            raise invalid from None
        # Password first, so an inactive Account costs (and answers) like a wrong password.
        if not (account.check_password(attrs["password"]) and account.is_active):
            raise invalid
        membership = Membership.objects.filter(
            school=self.context["school"], account=account, status=Membership.Status.ACTIVE
        ).first()
        if membership is None:
            raise invalid
        return {"account": account, "membership": membership}


class IdentifierField(serializers.CharField):
    """A VN mobile number or an email, normalised as Account stores it ("" is None)."""

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        if not raw:
            return None
        if "@" in raw:
            value = normalize_email(raw)
            try:
                validate_email(value)
            except DjangoValidationError:
                raise serializers.ValidationError("invalid_identifier") from None
            return value
        value = normalize_phone(raw)
        if not re.fullmatch(PHONE_PATTERN, value):
            raise serializers.ValidationError("invalid_identifier")
        return value


class ActivateSerializer(serializers.Serializer):
    """Accept an invitation on its School's host. With an existing Account for `identifier` the
    password must be that Account's (linking, never resetting); otherwise a new Account is made
    from `identifier`, `password` and `display_name` (default: the name on the invitation).
    Unknown, expired, revoked or used code, an identifier other than the invited one, a wrong
    password and an inactive Account all give the same error."""

    code = serializers.CharField(max_length=40)
    identifier = IdentifierField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    display_name = serializers.CharField(max_length=200, required=False)

    def validate(self, attrs):
        invalid = serializers.ValidationError(
            "Invalid or expired invitation.", code="invalid_invitation"
        )
        invitation = (
            Invitation.objects.select_for_update()
            .filter(code_digest=code_digest(attrs["code"]))
            .first()
        )
        identifier = attrs["identifier"]
        if (
            invitation is None
            or invitation.status != Invitation.Status.PENDING
            or invitation.is_expired
            or invitation.identifier not in (None, identifier)
        ):
            check_password(attrs["password"], _DUMMY_HASH)
            raise invalid
        key = "email" if "@" in identifier else "phone"
        account = Account.objects.filter(**{key: identifier}).first()
        if account is None:
            try:
                validate_password(attrs["password"])
            except DjangoValidationError as error:
                raise serializers.ValidationError({"password": error.messages}) from None
        elif not (account.check_password(attrs["password"]) and account.is_active):
            raise invalid
        return attrs | {"invitation": invitation, "account": account, "identifier_key": key}


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["name", "subdomain"]


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "display_name"]


class RoleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleAssignment
        fields = [
            "id",
            "role",
            "school_year",
            "subject_group",
            "school_class",
            "subject",
            "valid_from",
            "valid_to",
        ]


class TeachingPairSerializer(serializers.Serializer):
    subject = serializers.IntegerField()
    school_class = serializers.IntegerField()


class CapabilityScopeSerializer(serializers.Serializer):
    """Where an action applies: `kind` is a permissions `Scope` (or `enrolled_class`), and the ids
    say which groups, classes, subjects, pairs or students; school-wide scopes carry none."""

    kind = serializers.CharField()
    access = serializers.ChoiceField(["write", "read"])
    once_released = serializers.BooleanField()
    subject_groups = serializers.ListField(child=serializers.IntegerField(), required=False)
    school_classes = serializers.ListField(child=serializers.IntegerField(), required=False)
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False)
    students = serializers.ListField(child=serializers.IntegerField(), required=False)
    pairs = TeachingPairSerializer(many=True, required=False)


class CapabilitySerializer(serializers.Serializer):
    action = serializers.CharField()
    scopes = CapabilityScopeSerializer(many=True)


class MeSerializer(serializers.Serializer):
    account = AccountSerializer()
    school = SchoolSerializer()
    role_assignments = RoleAssignmentSerializer(many=True)
    capabilities = CapabilitySerializer(many=True)


def me_data(account, school, membership, actor) -> dict:
    return MeSerializer(
        {
            "account": account,
            "school": school,
            "role_assignments": RoleAssignment.objects.in_force()
            .filter(membership=membership)
            .order_by("id"),
            "capabilities": capabilities(actor),
        }
    ).data
