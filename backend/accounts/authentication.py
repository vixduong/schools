from drf_spectacular.authentication import SessionScheme
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed


class SchoolSessionAuthentication(SessionAuthentication):
    """Django session auth (CSRF enforced by the parent) that only accepts a session created at
    login on this School's host. Host-only cookies already keep browsers apart; this also
    rejects a replayed cookie value (sessions live in one global table)."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None and request.session.get("school_id") != request.school.pk:
            raise AuthenticationFailed("Session belongs to another School.")
        return result


class CsrfOnlyAuthentication(SessionAuthentication):
    """For login and logout: authenticates nobody but enforces CSRF, which plain DRF views skip
    for anonymous requests (login CSRF)."""

    def authenticate(self, request):
        self.enforce_csrf(request)
        return None


class SchoolSessionScheme(SessionScheme):
    """Lets drf-spectacular describe the subclass as the plain session-cookie scheme."""

    target_class = SchoolSessionAuthentication
