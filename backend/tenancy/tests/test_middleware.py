import pytest
from django.conf import settings
from django.db import connection

pytestmark = pytest.mark.usefixtures("as_app_role")


def names(response):
    return [p["name"] for p in response.json()]


def test_requests_run_as_the_app_role():
    with connection.cursor() as cur:
        cur.execute("SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cur.fetchone() == (settings.APP_DB_USER, False)


def test_school_host_sees_only_its_own_rows(client):
    assert names(client.get("/api/probes/", HTTP_HOST="a.localhost")) == ["a1", "a2"]
    assert names(client.get("/api/probes/", HTTP_HOST="b.localhost:8000")) == ["b1"]


def test_created_row_belongs_to_the_host_school(client):
    created = client.post("/api/probes/", {"name": "a3"}, HTTP_HOST="a.localhost")
    assert created.status_code == 201
    assert names(client.get("/api/probes/", HTTP_HOST="a.localhost")) == ["a1", "a2", "a3"]
    assert names(client.get("/api/probes/", HTTP_HOST="b.localhost")) == ["b1"]


@pytest.mark.parametrize("host", ["nope.localhost", "localhost", "a.b.localhost", "a.example.com"])
def test_unknown_host_is_404(client, host):
    assert client.get("/api/probes/", HTTP_HOST=host).status_code == 404


def test_no_scope_leaks_between_requests(client):
    client.get("/api/probes/", HTTP_HOST="a.localhost")
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM tenancy_probe")
        assert cur.fetchone()[0] == 0


@pytest.mark.urls("tenancy.tests.urls")
@pytest.mark.parametrize("query", ["", "?crash=1"])
def test_writes_roll_back_when_the_request_fails(client, query):
    client.raise_request_exception = False
    response = client.post("/api/fail/" + query, HTTP_HOST="a.localhost")
    assert response.status_code in (400, 500)
    assert "half-written" not in names(client.get("/api/probes/", HTTP_HOST="a.localhost"))


@pytest.mark.parametrize("host", ["A.LOCALHOST", "a.localhost.", "A.Localhost:8000"])
def test_host_case_and_trailing_dot(client, host):
    status = client.get("/api/probes/", HTTP_HOST=host).status_code
    assert status == (404 if host.endswith(".") else 200)
