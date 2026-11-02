"""Rate limits on sign-in and activation (docs/slices/slice-9.md). A middleware placed before
TenantMiddleware, so each count commits at once (autocommit): a refused login's rolled-back
savepoint cannot undo it, and no row lock is held while the password is checked (one school
network's sign-ins would otherwise queue behind each other). The two views accept JSON only, so
the identifier read here is the one they use."""

import json
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import normalize_email, normalize_phone

WINDOW = timedelta(minutes=15)
LIMITS = {"identifier": 10, "client": 50}
PATHS = {"/api/auth/login/", "/api/auth/activate/"}


def _identifier(request) -> str | None:
    """The identifier as the view will read it: decoded with the request's charset, and a JSON
    number taken as text (DRF's CharField accepts 84912345678)."""
    try:
        body = request.body.decode(request.encoding or settings.DEFAULT_CHARSET)
        raw = json.loads(body).get("identifier")
    except (ValueError, AttributeError, LookupError):
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = str(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return normalize_email(raw) if "@" in raw else normalize_phone(raw)


def client_address(request) -> str:
    """REMOTE_ADDR, or the proxy's header named by CLIENT_IP_HEADER (only where the proxy
    overwrites any copy the client sent, as Cloudflare does with CF-Connecting-IP)."""
    header = settings.CLIENT_IP_HEADER
    return (header and request.META.get(header)) or request.META.get("REMOTE_ADDR", "")


def _key(scope: str, value: str) -> str:
    return salted_hmac("accounts.attempt", f"{scope}:{value}", algorithm="sha256").hexdigest()


def _hit(key: str, window_start) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO accounts_attempt (key, window_start, count) VALUES (%s, %s, 1)"
            " ON CONFLICT (key, window_start)"
            " DO UPDATE SET count = accounts_attempt.count + 1 RETURNING count",
            [key, window_start],
        )
        count = cursor.fetchone()[0]
        if count == 1:  # a new window: forget the old ones
            cursor.execute(
                "DELETE FROM accounts_attempt WHERE window_start < %s", [window_start - WINDOW]
            )
    return count


class SignInRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or request.path not in PATHS:
            return self.get_response(request)
        now = timezone.now()
        window_start = now - (now - now.replace(minute=0, second=0, microsecond=0)) % WINDOW
        keys = {"client": _key("client", client_address(request))}
        if identifier := _identifier(request):
            keys["identifier"] = _key("identifier", identifier)
        counts = {scope: _hit(key, window_start) for scope, key in keys.items()}
        if any(count > LIMITS[scope] for scope, count in counts.items()):
            retry = int((window_start + WINDOW - now).total_seconds()) + 1
            response = JsonResponse({"detail": "too_many_attempts"}, status=429)
            response["Retry-After"] = str(retry)
            return response
        response = self.get_response(request)
        if 200 <= response.status_code < 300:
            # Only failures spend the budget: a school network's real sign-ins share one address.
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE accounts_attempt SET count = count - 1"
                    " WHERE key = ANY(%s) AND window_start = %s AND count > 0",
                    [list(keys.values()), window_start],
                )
        return response
