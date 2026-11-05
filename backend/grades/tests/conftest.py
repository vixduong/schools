"""Fixtures for the gradebook tests: School A with its terms, subjects, subject loads, teachers and
students, and helpers (as fixtures, so no test file imports another). Everything runs as the app
role (`as_app_role`), like production requests."""

import importlib
import time
from datetime import timedelta

import psycopg
import pytest
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, connection
from django.utils import timezone

from accounts.models import RoleAssignment
from grades.models import Gradebook, GradebookColumn
from schools.models import (
    AssessmentProfileVersion,
    Enrollment,
    GuardianLink,
    SubjectLoad,
    Term,
)
from schools.tests.factories import make_membership, make_student, make_subject
from tenancy.rls import school_scope
from testing import A, enroll, make_account, member, owner_role, sign_in

DAY = timedelta(days=1)
TODAY = timezone.localdate()


@pytest.fixture(autouse=True)
def _as_app_role(as_app_role):
    """Every test here runs as the NOBYPASSRLS app role."""


@pytest.fixture
def refused():
    """`refused("constraint_name", school, lambda: ...)`: the database refuses it by that name."""

    def check(constraint, school, make):
        with pytest.raises(IntegrityError, match=constraint), school_scope(school.pk):
            make()

    return check


@pytest.fixture
def profile_versions(transactional_db):
    """The Circular 22/2021 versions the migrations seed: transactional tests flush the global
    table, so they are rebuilt by running the migrations' own data steps (as the owner)."""
    seed = importlib.import_module("schools.migrations.0004_seed_secondary_assessment_profile")
    start = importlib.import_module("schools.migrations.0007_secondary_profile_from_2024")
    with owner_role():
        AssessmentProfileVersion.objects.all().delete()
        seed.seed(apps, None)
        start.apply(apps, None)


def teach(school, membership, subject, klass):
    return RoleAssignment.objects.create(
        school=school,
        membership=membership,
        role=RoleAssignment.Role.SUBJECT_TEACHER,
        school_year=klass.school_year,
        subject=subject,
        school_class=klass,
        valid_from=TODAY - 30 * DAY,
    )


def staff(school, email):
    account = make_account(email, display_name=email)
    with school_scope(school.pk):
        return make_membership(school, account)


@pytest.fixture
def w(schools, setup, admin, profile_versions):
    """School A. Terms HK I (year start to today + 100 days) and HK II (the rest of the year).
    MATH (scored, 70 periods in Grade 7: three regular columns) and PE (comment only). Class 7A
    (alice is its homeroom teacher): An and Bao since the year began, Dung since the year began
    until three days ago, Eve since three days ago. t1 teaches MATH and PE in 7A, t3 MATH in 7A too,
    t2 MATH in 7B."""
    a, _ = schools
    year, k7a, k7b = setup["year"], setup["7A"], setup["7B"]
    t1, t2, t3 = (staff(a, f"t{n}@example.com") for n in (1, 2, 3))
    with school_scope(a.pk):
        first = Term.objects.create(
            school=a,
            school_year=year,
            name="HK I",
            starts_on=year.starts_on,
            ends_on=TODAY + 100 * DAY,
        )
        second = Term.objects.create(
            school=a,
            school_year=year,
            name="HK II",
            starts_on=TODAY + 101 * DAY,
            ends_on=year.ends_on,
        )
        math, pe = make_subject(a, "MATH"), make_subject(a, "PE")
        pe.assessment = "comment_only"
        pe.save()
        for subject, periods in ((math, 70), (pe, 35)):
            SubjectLoad.objects.create(
                school=a,
                school_year=year,
                grade=k7a.grade,
                subject=subject,
                periods_per_year=periods,
            )
        teach(a, t1, math, k7a)
        teach(a, t1, pe, k7a)
        teach(a, t2, math, k7b)
        teach(a, t3, math, k7a)
        bao, dung, eve = (make_student(a, name) for name in ("Bao", "Dung", "Eve"))
        enroll(a, bao, k7a)
        Enrollment.objects.create(
            school=a,
            student=dung,
            school_year=year,
            school_class=k7a,
            valid_from=year.starts_on,
            valid_to=TODAY - 3 * DAY,
            reason_started=Enrollment.ReasonStarted.NEW_YEAR,
            reason_ended=Enrollment.ReasonEnded.CLASS_CHANGE,
        )
        Enrollment.objects.create(
            school=a,
            student=eve,
            school_year=year,
            school_class=k7a,
            valid_from=TODAY - 3 * DAY,
            reason_started=Enrollment.ReasonStarted.TRANSFER_IN,
        )
    return {
        **setup,
        "a": a,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "math": math,
        "pe": pe,
        "hk1": first,
        "hk2": second,
        "bao": bao,
        "dung": dung,
        "eve": eve,
    }


@pytest.fixture
def client_of():
    """`client_of("t1@example.com")`: a client signed in to School A."""
    return lambda email: sign_in(A, email)


@pytest.fixture
def board_member(schools):
    member(schools[0], make_account("board@example.com", display_name="Board"), "principal_board")
    return "board@example.com"


@pytest.fixture
def guardian_of_an(schools, w):
    account = make_account(None, "0912000009", "Mẹ của An")
    with school_scope(schools[0].pk):
        membership = make_membership(schools[0], account)
        GuardianLink.objects.create(
            school=schools[0],
            membership=membership,
            student=w["an"],
            relation="mother",
            valid_from=TODAY - 30 * DAY,
        )
    return "0912000009"


def api(client, method, path, body=None):
    return getattr(client, method)(
        f"/api/setup/{path}", body, content_type="application/json", HTTP_HOST=A
    )


@pytest.fixture
def call():
    """`call(client, "put", "gradebooks/1/cells/", body)`."""
    return api


@pytest.fixture
def open_book(call, w, client_of):
    """`open_book(term=..., subject=..., klass=...)`: t1 opens it through the API; the JSON."""

    def open_(term=None, subject=None, klass=None, client=None):
        response = call(
            client or client_of("t1@example.com"),
            "post",
            "gradebooks/",
            {
                "term": (term or w["hk1"]).pk,
                "subject": (subject or w["math"]).pk,
                "school_class": (klass or w["7A"]).pk,
            },
        )
        assert response.status_code in (200, 201), response.content
        return response.json()

    return open_


@pytest.fixture
def book(open_book):
    """MATH, 7A, HK I, opened by t1: its JSON."""
    return open_book()


def column_ids(book):
    """{("regular", 1): id, ...} of a gradebook's JSON."""
    return {(c["kind"], c["index"]): c["id"] for c in book["columns"]}


@pytest.fixture
def columns():
    return column_ids


@pytest.fixture
def save(call, client_of):
    """`save(book_id, cells, client=None)`: PUT the cells as t1 (a response)."""

    def put(book_id, cells, client=None):
        return call(
            client or client_of("t1@example.com"),
            "put",
            f"gradebooks/{book_id}/cells/",
            {"cells": cells},
        )

    return put


@pytest.fixture
def stored(schools):
    """Every score entry of School A as (column, student, value, result), oldest first."""
    from grades.models import ScoreEntry

    def read():
        with school_scope(schools[0].pk):
            return [
                (e.column_id, e.student_id, e.value, e.result)
                for e in ScoreEntry.objects.order_by("id")
            ]

    return read


@pytest.fixture
def make_raw_book(schools, w):
    """`make_raw_book(subject=MATH, term=HK I)`: a gradebook made straight in the database (3
    regular columns, a mid-term and an end-term) for the rules no API call can reach; the
    columns are made in the transaction that opens it, as the rule demands."""

    def make(subject=None, term=None):
        a = schools[0]
        with school_scope(a.pk):
            book = Gradebook.objects.create(
                school=a,
                school_year=w["year"],
                term=term or w["hk1"],
                subject=subject or w["math"],
                school_class=w["7A"],
                profile_version=AssessmentProfileVersion.objects.filter(
                    level_kind="lower_secondary"
                ).first(),
                opened_by=w["t1"],
            )
            cols = {
                (kind, index): GradebookColumn.objects.create(
                    school=a, gradebook=book, kind=kind, index=index
                )
                for kind, index in (
                    ("regular", 1),
                    ("regular", 2),
                    ("regular", 3),
                    ("mid_term", 1),
                    ("end_term", 1),
                )
            }
        return {"book": book, "columns": cols}

    return make


@pytest.fixture
def raw_book(make_raw_book):
    return make_raw_book()


@pytest.fixture
def second_conn(schools):
    """A second raw autocommit connection as the app role (see `app_conn` in the root conftest),
    for two transactions that overlap."""
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


@pytest.fixture
def lock_wait(second_conn):
    """`lock_wait()`: returns once some session is waiting for a lock (polled, never a sleep that
    hopes a thread got there); fails after `timeout` seconds."""

    def wait(timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            (waiting,) = second_conn.execute(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND wait_event_type = 'Lock'"
            ).fetchone()
            if waiting:
                return
            time.sleep(0.02)
        raise AssertionError("no session is waiting for a lock")

    return wait
