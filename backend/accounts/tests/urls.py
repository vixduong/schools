from django.http import JsonResponse
from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView


class Echo(APIView):
    """A POST view with the default authentication and permissions."""

    def post(self, request):
        return Response({"ok": True})


def whoami(request):
    """A plain Django view: sees only Django's request.user."""
    return JsonResponse({"authenticated": request.user.is_authenticated})


urlpatterns = [
    path("api/auth/", include("accounts.urls")),
    path("api/echo/", Echo.as_view()),
    path("whoami/", whoami),
]
