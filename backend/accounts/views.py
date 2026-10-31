from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import CsrfOnlyAuthentication
from .serializers import LoginSerializer, MeSerializer, me_data


class LoginView(APIView):
    authentication_classes = [CsrfOnlyAuthentication]
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
        return Response(me_data(account, request.school, membership))


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
        return Response(me_data(request.user, request.school, request.membership))


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={204: None})
    def get(self, request):
        get_token(request._request)  # makes CsrfViewMiddleware set the cookie
        return Response(status=204)
