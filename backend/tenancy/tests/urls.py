from django.urls import path
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from tenancy.models import Probe


class ProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Probe
        fields = ["id", "name"]


class ProbeList(generics.ListCreateAPIView):
    """Deliberately open (no permission): lets the tests exercise the middleware and RLS without
    accounts. Test URLconf only; the production URLconf has no open view."""

    # No school filter on purpose: isolation is enforced by RLS, not by this queryset.
    permission_classes = []
    queryset = Probe.objects.order_by("id")
    serializer_class = ProbeSerializer

    def perform_create(self, serializer):
        serializer.save(school=self.request.school)


class WriteThenFail(APIView):
    """Writes a row, then fails: the write must not survive."""

    permission_classes = []

    def post(self, request):
        Probe.objects.create(school=request.school, name="half-written")
        if request.query_params.get("crash"):
            raise RuntimeError("boom")
        raise ValidationError("row 50 is invalid")


urlpatterns = [
    path("api/probes/", ProbeList.as_view(), name="probe-list"),
    path("api/fail/", WriteThenFail.as_view()),
]
