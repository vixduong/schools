from rest_framework import serializers

from .models import Probe


class ProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Probe
        fields = ["id", "name"]
