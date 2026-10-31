from django.contrib.auth.hashers import check_password, make_password
from rest_framework import serializers

from tenancy.models import School

from .models import Account, Membership, RoleAssignment

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
            "scope_kind",
            "scope_id",
            "school_year",
            "valid_from",
            "valid_to",
        ]


class MeSerializer(serializers.Serializer):
    account = AccountSerializer()
    school = SchoolSerializer()
    role_assignments = RoleAssignmentSerializer(many=True)


def me_data(account, school, membership) -> dict:
    return MeSerializer(
        {
            "account": account,
            "school": school,
            "role_assignments": RoleAssignment.objects.in_force()
            .filter(membership=membership)
            .order_by("id"),
        }
    ).data
