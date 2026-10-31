from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("tenancy.urls")),
]
