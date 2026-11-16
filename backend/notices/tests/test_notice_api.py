"""Sending, listing and reading notices through the API, as the app role."""

import pytest

from audit.models import AuditEvent
from notices.models import Notice, NoticeRecipient
from permissions.actor import Actor
from permissions.engine import can
from permissions.matrix import Scope
from schools.models import SchoolClass, SubjectGroup
from schools.tests.factories import make_class, make_year
from tenancy.rls import school_scope
from testing import A, make_account, sign_in

from .conftest import Role, assign

pytestmark = pytest.mark.usefixtures("as_app_role")

URL = "/api/setup/notices/"


def client_of(name):
    return sign_in(A, f"{name}@example.com")


def call(client, method, path="", body=None, **query):
    suffix = "?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else ""
    return getattr(client, method)(
        f"{URL}{path}{suffix}", body, content_type="application/json", HTTP_HOST=A
    )


def send(name, audience, **fields):
    body = {"audience": audience, "title": "Họp phụ huynh", "body": "Thứ Bảy, 8 giờ.", **fields}
    return call(client_of(name), "post", "", body)


def to_class(world, key="7A"):
    return {"school_class": world[key].pk}


def to_group(world, key="math_group"):
    return {"subject_group": world[key].pk}


def count_in(world, model):
    with school_scope(world["school"].pk):
        return model.objects.count()


# --- who may send what -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sender", "audience", "target", "reached"),
    [
        ("admin", "school", None, 6),
        ("board", "school", None, 6),
        ("gl_math", "group", "math_group", 1),
        ("hr_7a", "homeroom_guardians", "7A", 2),
        ("t_math", "class", "7A", 4),
    ],
)
def test_each_sender_reaches_the_audience_their_row_opens(world, sender, audience, target, reached):
    fields = {}
    if audience == "group":
        fields = to_group(world, target)
    elif target:
        fields = to_class(world, target)
    response = send(sender, audience, **fields)
    assert response.status_code == 201, response.json()
    sent = response.json()
    assert (sent["audience"], sent["recipient_count"], sent["read_count"]) == (
        audience,
        reached,
        0,
    )
    assert sent["title"] == "Họp phụ huynh" and sent["sender_name"]


@pytest.mark.parametrize(
    ("sender", "audience", "target"),
    [
        ("hr_7a", "class", "7A"),  # a homeroom-only teacher is not "own classes"
        ("t_math", "homeroom_guardians", "7A"),  # a subject-only teacher is not the homeroom
        ("t_lit", "class", "7A"),  # teaches 7B only
        ("hr_7a", "school", None),
        ("gl_math", "school", None),
        ("gl_lit", "group", "math_group"),  # leads another group
        ("g_an", "class", "7A"),
        ("s_an", "school", None),
        ("nobody", "school", None),
    ],
)
def test_a_sender_outside_the_audience_is_refused(world, sender, audience, target):
    fields = {}
    if audience == "group":
        fields = to_group(world, target)
    elif target:
        fields = to_class(world, target)
    assert send(sender, audience, **fields).status_code == 403
    assert count_in(world, Notice) == 0


# --- the 400s --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "errors"),
    [
        ({"audience": "everyone"}, {"audience": ["unknown"]}),
        ({"audience": ""}, {"audience": ["unknown"]}),
        ({"title": ""}, {"title": ["required"]}),
        ({"title": "  "}, {"title": ["required"]}),
        ({"title": "x" * 201}, {"title": ["too_long"]}),
        ({"title": "a\nb"}, {"title": ["single_line"]}),
        ({"title": "a\rb"}, {"title": ["single_line"]}),
        ({"body": ""}, {"body": ["required"]}),
        ({"body": "x" * 5001}, {"body": ["too_long"]}),
    ],
)
def test_a_notice_is_validated(world, fields, errors):
    response = send(
        "admin",
        fields.get("audience", "school"),
        **{k: v for k, v in fields.items() if k != "audience"},
    )
    assert response.status_code == 400 and response.json() == errors
    assert count_in(world, Notice) == 0


def test_a_missing_field_is_required(world):
    response = call(client_of("admin"), "post", "", {})
    assert response.status_code == 400
    assert response.json() == {
        "audience": ["required"],
        "title": ["required"],
        "body": ["required"],
    }


def test_a_target_the_school_does_not_have_is_unknown_before_anyone_decides(schools, world):
    with school_scope(schools[1].pk):
        other = make_class(schools[1], make_year(schools[1]), "9Z")
    for target in (9_999_999, other.pk):  # nowhere, and another School's class
        response = send("hr_7a", "class", school_class=target)
        assert (response.status_code, response.json()) == (400, {"school_class": ["unknown"]})
    response = send("gl_math", "group", subject_group=9_999_999)
    assert (response.status_code, response.json()) == (400, {"subject_group": ["unknown"]})
    assert count_in(world, Notice) == 0


def test_a_class_audience_needs_its_class_and_a_group_audience_its_group(world):
    assert send("hr_7a", "class").json() == {"school_class": ["required"]}
    assert send("gl_math", "group").json() == {"subject_group": ["required"]}


def test_a_target_the_audience_does_not_use_is_a_constraint_error(world):
    response = send("admin", "school", **to_class(world))
    assert response.status_code == 400
    assert response.json() == {"constraint": ["notice_target_fits_audience"]}


def test_an_audience_that_reaches_nobody_leaves_no_notice_and_no_audit_event(schools, world):
    a = schools[0]
    account = make_account("hr_7c@example.com", display_name="Homeroom 7C")
    with school_scope(a.pk):
        from accounts.models import Membership

        membership = Membership.objects.create(school=a, account=account)
        empty = make_class(a, make_year(a), "7C")
        assign(a, membership, Role.HOMEROOM_TEACHER, school_class=empty)
    response = send("hr_7c", "homeroom_guardians", school_class=empty.pk)
    assert (response.status_code, response.json()) == (400, {"recipients": ["none"]})
    assert count_in(world, Notice) == 0 and count_in(world, NoticeRecipient) == 0
    with school_scope(a.pk):
        assert not AuditEvent.objects.filter(target_table="notices_notice").exists()


# --- reading ---------------------------------------------------------------------------------


def test_a_recipient_lists_its_notices_newest_first_and_a_stranger_none(world):
    assert send("hr_7a", "homeroom_guardians", **to_class(world), title="Một").status_code == 201
    assert send("t_math", "class", **to_class(world), title="Hai").status_code == 201
    mine = call(client_of("g_an"), "get").json()
    assert [n["title"] for n in mine] == ["Hai", "Một"]
    assert set(mine[0]) == {"id", "title", "body", "sent_at", "sender_name", "audience", "read_at"}
    assert mine[0]["read_at"] is None
    # A student gets the class notice only (the first one is the Guardians').
    assert [n["title"] for n in call(client_of("s_an"), "get").json()] == ["Hai"]
    assert call(client_of("g_binh"), "get").json() == []
    assert call(client_of("t_math"), "get").json() == []  # the sender reads what they sent below


def test_a_sender_lists_what_it_sent_with_counts_and_never_who_read(world):
    sent = send("t_math", "class", **to_class(world)).json()
    pk = sent["id"]
    assert call(client_of("g_an"), "post", f"{pk}/read/").status_code == 200
    (mine,) = call(client_of("t_math"), "get", sent=1).json()
    assert (mine["recipient_count"], mine["read_count"]) == (4, 1)
    assert mine["school_class_name"] == "7A" and mine["subject_group_name"] is None
    assert not {"recipients", "read_at", "read_by"} & set(mine)
    assert call(client_of("g_an"), "get", sent=1).json() == []


def test_a_notice_is_marked_read_once(world):
    pk = send("hr_7a", "homeroom_guardians", **to_class(world)).json()["id"]
    first = call(client_of("g_an"), "post", f"{pk}/read/")
    assert first.status_code == 200 and first.json()["read_at"] is not None
    again = call(client_of("g_an"), "post", f"{pk}/read/")
    assert again.status_code == 200 and again.json()["read_at"] == first.json()["read_at"]
    assert call(client_of("g_an"), "get").json()[0]["read_at"] == first.json()["read_at"]
    # The other Guardian's mark is their own.
    assert call(client_of("g_chi"), "get").json()[0]["read_at"] is None


def test_only_a_recipient_can_mark_a_notice_read(world):
    pk = send("hr_7a", "homeroom_guardians", **to_class(world)).json()["id"]
    for stranger in ("g_binh", "hr_7a", "s_an", "admin"):
        assert call(client_of(stranger), "post", f"{pk}/read/").status_code == 404
    assert call(client_of("g_an"), "post", "999999/read/").status_code == 404


def test_a_notice_of_another_school_is_not_found(schools, world):
    pk = send("hr_7a", "homeroom_guardians", **to_class(world)).json()["id"]
    account = make_account("b@example.com", display_name="B")
    from accounts.models import Membership

    with school_scope(schools[1].pk):
        Membership.objects.create(school=schools[1], account=account)
    client = sign_in("b.localhost", "b@example.com")
    response = client.post(
        f"{URL}{pk}/read/", {}, content_type="application/json", HTTP_HOST="b.localhost"
    )
    assert response.status_code == 404


# --- audiences/ ------------------------------------------------------------------------------

ROLE_OF = {
    "admin": "school_admin",
    "board": "principal_board",
    "gl_math": "group_leader",
    "gl_lit": "group_leader",
    "hr_7a": "homeroom_teacher",
    "t_math": "subject_teacher",
    "t_lit": "subject_teacher",
    "g_an": "guardian",
    "s_an": "student",
    "nobody": "nobody",
}


@pytest.mark.parametrize("who", ROLE_OF)
def test_the_audiences_listed_are_exactly_what_can_allows(world, who):
    listed = call(client_of(who), "get", "audiences/").json()
    actor = Actor(world["m"][who])
    school = world["school"]
    with school_scope(school.pk):
        allowed = []
        if can(actor, "notices.send", school, scope=Scope.SCHOOL):
            allowed.append({"audience": "school"})
        for group in SubjectGroup.objects.order_by("name", "id"):
            if can(actor, "notices.send", group, scope=Scope.GROUP_SUBJECTS):
                allowed.append(
                    {"audience": "group", "subject_group": {"id": group.pk, "name": group.name}}
                )
        for klass in SchoolClass.objects.order_by("name", "id"):
            for audience, scope in (
                ("homeroom_guardians", Scope.HOMEROOM_CLASS),
                ("class", Scope.TEACHING_CLASSES),
            ):
                if can(actor, "notices.send", klass, scope=scope):
                    allowed.append(
                        {
                            "audience": audience,
                            "school_class": {"id": klass.pk, "name": klass.name},
                        }
                    )
    key = lambda e: (e["audience"], str(e))  # noqa: E731
    assert sorted(listed, key=key) == sorted(allowed, key=key)
    # Each listed audience is sendable (and a member who may send nothing lists nothing).
    assert (listed == []) == (ROLE_OF[who] in ("guardian", "student", "nobody"))
