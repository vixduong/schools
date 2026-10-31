"""No DRF view is open by accident: every one in the production URLconf has School-bound
authentication and a real permission, except an explicit allowlist."""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from drf_spectacular.views import SpectacularAPIView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from accounts.authentication import CsrfOnlyAuthentication, SchoolSessionAuthentication
from accounts.views import CsrfView, LoginView, LogoutView, MeView

ALLOWED_AUTHENTICATION = {SchoolSessionAuthentication, CsrfOnlyAuthentication}
# Open on purpose: sign-in has no session yet, and the schema describes the public API.
MAY_ALLOW_ANY = {LoginView, LogoutView, CsrfView, SpectacularAPIView}


def api_views(patterns=None):
    for pattern in get_resolver().url_patterns if patterns is None else patterns:
        if isinstance(pattern, URLResolver):
            yield from api_views(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            view = getattr(pattern.callback, "cls", None)
            if view is not None and issubclass(view, APIView):
                yield view


def problems(view):
    found = []
    extra = set(view.authentication_classes) - ALLOWED_AUTHENTICATION
    if extra:
        found.append(f"authentication_classes has {sorted(c.__name__ for c in extra)}")
    permissions = list(view.permission_classes)
    if not permissions:
        found.append("permission_classes is empty")
    if AllowAny in permissions and view not in MAY_ALLOW_ANY:
        found.append("AllowAny is not allowed here")
    return found


def test_production_urlconf_has_views_to_check():
    assert {LoginView, LogoutView, CsrfView, MeView, SpectacularAPIView} <= set(api_views())


@pytest.mark.parametrize("view", sorted(set(api_views()), key=lambda v: v.__qualname__))
def test_view_is_not_open(view):
    assert problems(view) == []


def test_the_guard_catches_open_views():
    class PlainSession(APIView):
        authentication_classes = [SessionAuthentication]
        permission_classes = [IsAuthenticated]

    class NoPermission(APIView):
        permission_classes = []

    class Anyone(APIView):
        permission_classes = [AllowAny]

    assert len(problems(PlainSession)) == 1
    assert problems(NoPermission) == ["permission_classes is empty"]
    assert problems(Anyone) == ["AllowAny is not allowed here"]
