"""No DRF view is open by accident: every one in the production URLconf has School-bound
authentication and a real permission, except an explicit allowlist."""

from dataclasses import dataclass

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from drf_spectacular.views import SpectacularAPIView
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from accounts.authentication import CsrfOnlyAuthentication, SchoolSessionAuthentication
from accounts.permissions import HasMembership
from accounts.views import ActivateView, CsrfView, LoginView, LogoutView, MeView
from permissions.drf import Can, CanPermission

ALLOWED_AUTHENTICATION = {SchoolSessionAuthentication, CsrfOnlyAuthentication}
# Open on purpose: sign-in and activation have no session yet; the schema describes the public
# API.
MAY_ALLOW_ANY = {LoginView, LogoutView, ActivateView, CsrfView, SpectacularAPIView}


@dataclass(frozen=True)
class Route:
    """A URL's view as it runs: a `@action(permission_classes=..., authentication_classes=...)`
    override reaches the view through the route's initkwargs, not through the class."""

    view: type
    name: str
    authentication_classes: tuple
    permission_classes: tuple


def routes(patterns=None):
    for pattern in get_resolver().url_patterns if patterns is None else patterns:
        if isinstance(pattern, URLResolver):
            yield from routes(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            view = getattr(pattern.callback, "cls", None)
            if view is not None and issubclass(view, APIView):
                kwargs = getattr(pattern.callback, "initkwargs", {})
                yield Route(
                    view,
                    f"{view.__qualname__}:{pattern.name}",
                    tuple(kwargs.get("authentication_classes", view.authentication_classes)),
                    tuple(kwargs.get("permission_classes", view.permission_classes)),
                )


def api_views():
    return {route.view for route in routes()}


def problems(view):
    found = []
    extra = set(view.authentication_classes) - ALLOWED_AUTHENTICATION
    if extra:
        found.append(f"authentication_classes has {sorted(c.__name__ for c in extra)}")
    permissions = list(view.permission_classes)
    if not permissions:
        found.append("permission_classes is empty")
    if AllowAny in permissions and getattr(view, "view", view) not in MAY_ALLOW_ANY:
        found.append("AllowAny is not allowed here")
    real = (HasMembership, CanPermission)  # `Can(...)` builds a CanPermission subclass
    if (
        permissions
        and AllowAny not in permissions
        and not any(issubclass(p, real) for p in permissions)
    ):
        found.append("no HasMembership or Can(...) permission")
    return found


def test_production_urlconf_has_views_to_check():
    assert {LoginView, LogoutView, CsrfView, MeView, SpectacularAPIView} <= api_views()


ALL_ROUTES = sorted(set(routes()), key=lambda r: r.name)


def test_the_action_routes_are_among_those_checked():
    names = {route.name for route in ALL_ROUTES}
    assert {
        "SchoolYearViewSet:school-years-close",
        "RoleAssignmentViewSet:role-assignments-confirm",
    } <= names


@pytest.mark.parametrize("route", ALL_ROUTES, ids=lambda r: r.name)
def test_route_is_not_open(route):
    assert problems(route) == []


def test_the_guard_catches_open_views():
    class PlainSession(APIView):
        authentication_classes = [SessionAuthentication]
        permission_classes = [HasMembership]

    class NoPermission(APIView):
        permission_classes = []

    class Anyone(APIView):
        permission_classes = [AllowAny]

    class Authenticated(APIView):
        permission_classes = [IsAuthenticated]

    class Checked(APIView):
        permission_classes = [HasMembership, Can("school.configure")]

    assert len(problems(PlainSession)) == 1
    assert problems(NoPermission) == ["permission_classes is empty"]
    assert problems(Anyone) == ["AllowAny is not allowed here"]
    assert problems(Authenticated) == ["no HasMembership or Can(...) permission"]
    assert problems(Checked) == []


def test_the_guard_catches_an_action_that_overrides_the_permissions():
    class Opened(viewsets.ViewSet):
        permission_classes = [HasMembership, Can("school.configure")]

        @action(detail=False, permission_classes=[AllowAny])
        def anyone(self, request): ...

        @action(detail=False, authentication_classes=[SessionAuthentication])
        def plain_session(self, request): ...

        @action(detail=False, permission_classes=[HasMembership])
        def fine(self, request): ...

    router = DefaultRouter()
    router.register("opened", Opened, basename="opened")
    found = {route.name.split(":")[1]: problems(route) for route in routes(router.urls)}
    assert found["opened-anyone"] == ["AllowAny is not allowed here"]
    assert len(found["opened-plain-session"]) == 1
    assert found["opened-fine"] == []
