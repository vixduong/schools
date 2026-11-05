from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/auth/", include("accounts.urls")),
    path("api/setup/", include("schools.urls")),
    path("api/setup/", include("audit.urls")),
    path("api/setup/", include("timetable.urls")),
    path("api/setup/", include("grades.urls")),
]
