from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView


class Echo(APIView):
    """A POST view with the default authentication and permissions."""

    def post(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("api/auth/", include("accounts.urls")),
    path("api/echo/", Echo.as_view()),
]
