from rest_framework import generics

from .models import Probe
from .serializers import ProbeSerializer


class ProbeList(generics.ListCreateAPIView):
    # No school filter on purpose: isolation is enforced by RLS, not by this queryset.
    queryset = Probe.objects.order_by("id")
    serializer_class = ProbeSerializer

    def perform_create(self, serializer):
        serializer.save(school=self.request.school)
