from django.urls import path

from .views import ProbeList

urlpatterns = [path("probes/", ProbeList.as_view(), name="probe-list")]
