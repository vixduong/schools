from django.core.exceptions import ImproperlyConfigured

_VALUES = {"1": True, "true": True, "0": False, "false": False}


def parse_secure_cookies(raw: str | None, debug: bool) -> bool:
    """SECURE_COOKIES: unset means true; only 1/true/0/false (any case) are accepted, so a typo
    cannot switch the Secure flag and __Host- prefix off. Off is refused when DEBUG is off."""
    if raw is None:
        return True
    try:
        secure = _VALUES[raw.lower()]
    except KeyError:
        raise ImproperlyConfigured(
            f"SECURE_COOKIES must be one of 1, true, 0, false (got {raw!r})."
        ) from None
    if not secure and not debug:
        raise ImproperlyConfigured("SECURE_COOKIES=false is only allowed with DJANGO_DEBUG=1.")
    return secure
