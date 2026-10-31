import pytest
from django.core.exceptions import ImproperlyConfigured

from config.cookies import parse_secure_cookies


@pytest.mark.parametrize(
    "raw, debug, expected",
    [
        (None, False, True),
        (None, True, True),
        ("1", False, True),
        ("true", False, True),
        ("TRUE", False, True),
        ("0", True, False),
        ("false", True, False),
        ("False", True, False),
    ],
)
def test_parses_accepted_values(raw, debug, expected):
    assert parse_secure_cookies(raw, debug) is expected


@pytest.mark.parametrize("raw", ["", "yes", "no", "off", "2", " 1", "flase"])
def test_anything_else_raises(raw):
    with pytest.raises(ImproperlyConfigured, match="must be one of"):
        parse_secure_cookies(raw, True)


@pytest.mark.parametrize("raw", ["0", "false"])
def test_insecure_cookies_are_refused_outside_debug(raw):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_DEBUG"):
        parse_secure_cookies(raw, False)
