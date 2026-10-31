from contextlib import contextmanager

import psycopg
import pytest
from django.conf import settings
from django.db import connection

from tenancy.models import Probe, School
from tenancy.rls import school_scope


@pytest.fixture
def schools(transactional_db):
    """School A with two probes, School B with one. Committed, so other connections see them."""
    a = School.objects.create(name="A", subdomain="a")
    b = School.objects.create(name="B", subdomain="b")
    for school, names in ((a, ["a1", "a2"]), (b, ["b1"])):
        with school_scope(school.pk):
            Probe.objects.bulk_create([Probe(school=school, name=n) for n in names])
    return a, b


@pytest.fixture
def app_conn(schools):
    """Raw autocommit connection to the test database as the NOBYPASSRLS app role."""
    d = connection.settings_dict
    conn = psycopg.connect(
        dbname=d["NAME"],
        host=d["HOST"],
        port=d["PORT"],
        user=settings.APP_DB_USER,
        password=settings.APP_DB_PASSWORD,
        autocommit=True,
    )
    yield conn
    conn.close()


@contextmanager
def db_role(user, password):
    """Run Django's own connection as another DB role for the duration of the block."""
    d = connection.settings_dict
    previous = (d["USER"], d["PASSWORD"])
    connection.close()
    d["USER"], d["PASSWORD"] = user, password
    try:
        yield
    finally:
        connection.close()
        d["USER"], d["PASSWORD"] = previous


def owner_role():
    """For test setup the app role may not do (it cannot create or edit Accounts)."""
    return db_role(settings.OWNER_DB_USER, settings.OWNER_DB_PASSWORD)


@pytest.fixture
def as_app_role(schools):
    """Run Django's own connection as the app role, like production requests do."""
    with db_role(settings.APP_DB_USER, settings.APP_DB_PASSWORD):
        yield
