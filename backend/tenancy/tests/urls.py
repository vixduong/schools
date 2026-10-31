from django.urls import include, path
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from tenancy.models import Probe


class WriteThenFail(APIView):
    """Writes a row, then fails: the write must not survive."""

    def post(self, request):
        Probe.objects.create(school=request.school, name="half-written")
        if request.query_params.get("crash"):
            raise RuntimeError("boom")
        raise ValidationError("row 50 is invalid")


urlpatterns = [
    path("api/", include("tenancy.urls")),
    path("api/fail/", WriteThenFail.as_view()),
]
