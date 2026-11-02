from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from permissions.actor import Actor
from schools.views import database_rules
from tenancy.rls import set_actor

from .authentication import CsrfOnlyAuthentication
from .invitations import accept
from .models import Account
from .serializers import (
    ActivateSerializer,
    LoginSerializer,
    MeSerializer,
    SchoolSerializer,
    me_data,
)


class LoginView(APIView):
    authentication_classes = [CsrfOnlyAuthentication]
    # JSON only: the rate limiter reads the identifier from the same body (accounts.ratelimit).
    parser_classes = [JSONParser]
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses=MeSerializer, auth=[])
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"school": request.school})
        serializer.is_valid(raise_exception=True)
        account = serializer.validated_data["account"]
        membership = serializer.validated_data["membership"]
        login(request._request, account)
        # After login(): it flushes a session that belongs to someone else.
        request.session["school_id"] = request.school.pk
        return Response(me_data(account, request.school, membership, Actor(membership)))


class ActivateView(APIView):
    """Accept an invitation and sign in. Everything is written in one savepoint (Account when
    new, Membership, roles or link, invitation `accepted`); the session key rotates last.
    The only view that creates an Account (a test scans for others)."""

    parser_classes = [JSONParser]  # as LoginView: the rate limiter reads this body
    authentication_classes = [CsrfOnlyAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(request=ActivateSerializer, responses=MeSerializer, auth=[])
    def post(self, request):
        serializer = ActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invitation, account = data["invitation"], data["account"]
        set_actor("activation")
        with database_rules():
            if account is None:
                account = Account(
                    display_name=data.get("display_name") or invitation.display_name,
                    **{data["identifier_key"]: data["identifier"]},
                )
                account.set_password(data["password"])
                account.save()
            membership = accept(invitation, account)
        login(request._request, account)
        request.session["school_id"] = request.school.pk
        return Response(me_data(account, request.school, membership, Actor(membership)))


class LogoutView(APIView):
    authentication_classes = [CsrfOnlyAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, auth=[])
    def post(self, request):
        logout(request._request)
        return Response(status=204)


class MeView(APIView):
    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(
            me_data(request.user, request.school, request.membership, Actor.of(request))
        )


class SchoolView(APIView):
    """The School of this host, for the login screen to lead with before anyone signs in. Only
    the name and subdomain are public."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=SchoolSerializer, auth=[])
    def get(self, request):
        return Response(SchoolSerializer(request.school).data)


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={204: None})
    def get(self, request):
        get_token(request._request)  # makes CsrfViewMiddleware set the cookie
        return Response(status=204)
