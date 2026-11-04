"""Leave requests (checks, exclusion, lifecycle trigger, grants, audit) and API, as the app role."""

# `world` and `class_7a` are fixtures imported by name, so each test taking one "redefines" it.
# ruff: noqa: F811, F401

from datetime import timedelta
from itertools import count

import pytest
from django.db import DataError, ProgrammingError
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from audit.models import AuditEvent
from schools.models import GuardianLink
from schools.tests.factories import make_membership
from tenancy.rls import school_scope
from testing import A, make_account, member, owner_role, sign_in
from timetable.models import LeaveRequest
from timetable.tests.test_attendance import class_7a, put, sheet, sheet_url, stored
from timetable.tests.test_timetable import TODAY, refused, teach, teacher, world

pytestmark = pytest.mark.usefixtures("as_app_role")

DAY = timedelta(days=1)
WEEK = 7 * DAY
Status = LeaveRequest.Status
TABLE = "timetable_leaverequest"
LEAVE_URL = "/api/setup/leave-requests/"


def guardian(school, student, phone):
    """A Guardian signing in by phone, linked to `student` since a month: their Membership."""
    account = make_account(None, phone, f"Guardian {phone[-1]}")
    with school_scope(school.pk):
        membership = make_membership(school, account)
        GuardianLink.objects.create(
            school=school,
            membership=membership,
            student=student,
            relation="mother",
            valid_from=TODAY - 30 * DAY,
        )
    return membership


def homeroom_of_7b(school, world, email):
    account = make_account(email, display_name="Homeroom 7B")
    with school_scope(school.pk):
        membership = make_membership(school, account)
        RoleAssignment.objects.create(
            school=school,
            membership=membership,
            role=RoleAssignment.Role.HOMEROOM_TEACHER,
            school_year=world["year"],
            school_class=world["7B"],
            valid_from=TODAY - 30 * DAY,
        )
    return membership


def leave(school, sender, student, from_on=TODAY, to_on=None, **fields):
    """A request as stored (an insert), waiting unless `fields` says otherwise."""
    with school_scope(school.pk):
        return LeaveRequest.objects.create(
            school=school,
            student=student,
            sent_by=sender,
            from_on=from_on,
            to_on=to_on or from_on,
            reason="ốm",
            **fields,
        )


def audited(school):
    with school_scope(school.pk):
        return list(AuditEvent.objects.filter(target_table=TABLE).order_by("id"))


@pytest.fixture
def parents(schools, class_7a):
    """Guardians: `an_mother` and `an_father` of An (7A), `binh_mother` of Binh (7B)."""
    a, _ = schools
    return {
        "an_mother": guardian(a, class_7a["an"], "0912000002"),
        "an_father": guardian(a, class_7a["an"], "0912000003"),
        "binh_mother": guardian(a, class_7a["binh"], "0912000004"),
    }


# --- the database rules ---------------------------------------------------------------------


def test_a_request_covers_whole_days_up_to_30_and_has_a_reason(schools, class_7a, parents):
    a, _ = schools
    an, mother = class_7a["an"], parents["an_mother"]
    cases = {
        "leaverequest_to_on_after_from_on": {"from_on": TODAY + DAY, "to_on": TODAY},
        "leaverequest_at_most_30_days": {"from_on": TODAY, "to_on": TODAY + 30 * DAY},
        "leaverequest_reason_not_empty": {"reason": ""},
    }
    refused(
        "leaverequest_decision_matches_status", a, lambda: leave_with(a, mother, an, status="lost")
    )
    for name, fields in cases.items():
        refused(name, a, lambda fields=fields: leave_with(a, mother, an, **fields))
    with pytest.raises(DataError), school_scope(a.pk):
        leave_with(a, mother, an, reason="x" * 501)
    with school_scope(a.pk):  # 30 days, first and last included, is the longest
        leave_with(a, mother, an, from_on=TODAY, to_on=TODAY + 29 * DAY)


def leave_with(school, sender, student, **fields):
    """Like `leave`, inside the caller's scope, with `fields` replacing the defaults."""
    defaults = {"from_on": TODAY, "to_on": TODAY, "reason": "ốm"}
    return LeaveRequest.objects.create(
        school=school, student=student, sent_by=sender, **{**defaults, **fields}
    )


def test_a_decision_is_recorded_exactly_when_the_request_is_approved_or_declined(
    schools, class_7a, parents
):
    a, _ = schools
    an, mother, homeroom = class_7a["an"], parents["an_mother"], class_7a["t1"]
    when = timezone.now()
    decision = {"decided_by": homeroom, "decided_at": when}
    for fields in (
        {"status": Status.APPROVED},  # no decider
        {"status": Status.DECLINED, "decided_by": homeroom},  # no time
        {"status": Status.WAITING, **decision},  # a decision on a waiting request
        {"status": Status.CANCELLED, **decision},  # or on a cancelled one
    ):
        refused(
            "leaverequest_decision_matches_status",
            a,
            lambda fields=fields: leave_with(a, mother, an, decision_comment="x", **fields),
        )
    refused(
        "leaverequest_declined_has_comment",
        a,
        lambda: leave_with(a, mother, an, status=Status.DECLINED, **decision),
    )
    with school_scope(a.pk):
        leave_with(a, mother, an, status=Status.DECLINED, decision_comment="không", **decision)
        leave_with(
            a,
            mother,
            an,
            from_on=TODAY + WEEK,
            to_on=TODAY + WEEK,
            status=Status.APPROVED,
            **decision,
        )


def test_a_student_has_one_live_request_per_day(schools, class_7a, parents):
    a, _ = schools
    an, binh, mother = class_7a["an"], class_7a["binh"], parents["an_mother"]
    homeroom, when = class_7a["t1"], timezone.now()
    first = leave(a, mother, an, TODAY, TODAY + 2 * DAY)
    for start, end in ((TODAY - DAY, TODAY), (TODAY + 2 * DAY, TODAY + 3 * DAY), (TODAY, TODAY)):
        refused(
            "leaverequest_no_overlap",
            a,
            lambda start=start, end=end: leave_with(a, mother, an, from_on=start, to_on=end),
        )
    with school_scope(a.pk):
        leave_with(a, mother, an, from_on=TODAY + 3 * DAY, to_on=TODAY + 3 * DAY)  # the next day
        leave_with(a, mother, binh)  # another student
        # An approved request holds its days too.
        LeaveRequest.objects.filter(pk=first.pk).update(
            status=Status.APPROVED, decided_by=homeroom, decided_at=when
        )
    refused("leaverequest_no_overlap", a, lambda: leave_with(a, mother, an))
    # A declined or cancelled request frees its days: a stored one does not hold them either.
    with school_scope(a.pk):
        leave_with(
            a,
            mother,
            an,
            status=Status.DECLINED,
            decided_by=homeroom,
            decided_at=when,
            decision_comment="không",
        )
        leave_with(a, mother, an, status=Status.CANCELLED)


def test_a_declined_or_cancelled_request_frees_its_days(schools, class_7a, parents):
    a, _ = schools
    an, mother, homeroom = class_7a["an"], parents["an_mother"], class_7a["t1"]
    declined = leave(a, mother, an, TODAY, TODAY + DAY)
    refused("leaverequest_no_overlap", a, lambda: leave_with(a, mother, an))
    with school_scope(a.pk):
        LeaveRequest.objects.filter(pk=declined.pk).update(
            status=Status.DECLINED,
            decided_by=homeroom,
            decided_at=timezone.now(),
            decision_comment="không",
        )
        cancelled = leave_with(a, mother, an)
        LeaveRequest.objects.filter(pk=cancelled.pk).update(status=Status.CANCELLED)
        leave_with(a, mother, an, from_on=TODAY, to_on=TODAY + 2 * DAY)


def touch(pk, **fields):
    """An update, inside the caller's scope."""
    return LeaveRequest.objects.filter(pk=pk).update(**fields)


def change(school, pk, **fields):
    with school_scope(school.pk):
        return touch(pk, **fields)


def test_only_a_waiting_request_changes_and_only_to_a_decision_or_a_cancel(
    schools, class_7a, parents
):
    a, _ = schools
    an, mother, homeroom = class_7a["an"], parents["an_mother"], class_7a["t1"]
    decision = {"decided_by": homeroom, "decided_at": timezone.now()}
    approved = {"status": Status.APPROVED, **decision}
    declined = {"status": Status.DECLINED, "decision_comment": "không", **decision}
    cancelled = {"status": Status.CANCELLED}
    days = count(0, 40)  # a request of its own, so none holds another's days

    def waiting():
        return leave(a, mother, an, TODAY + next(days) * DAY).pk

    # Each way out of waiting, once.
    for outcome in (approved, declined, cancelled):
        change(a, waiting(), **outcome)
    # Nothing leaves approved, declined or cancelled; a waiting one does not "change" to waiting.
    cases = [
        (approved, {"status": Status.CANCELLED, "decided_by": None, "decided_at": None}),
        (approved, declined),
        (declined, approved),
        (declined, {"status": Status.WAITING, "decided_by": None, "decided_at": None}),
        (cancelled, {"status": Status.WAITING}),
        (cancelled, approved),
        (approved, {"decision_comment": "đã duyệt"}),  # not even a comment
        (None, {"status": Status.WAITING}),
    ]
    for first, second in cases:
        pk = waiting()
        if first:
            change(a, pk, **first)
        refused("leaverequest_lifecycle", a, lambda pk=pk, second=second: touch(pk, **second))


def test_a_request_never_changes_what_it_asked_for(schools, class_7a, parents):
    a, _ = schools
    an, binh, mother = class_7a["an"], class_7a["binh"], parents["an_mother"]
    pk = leave(a, mother, an).pk
    edits = {
        "student_id": binh.pk,
        "sent_by_id": parents["an_father"].pk,
        "from_on": TODAY + DAY,
        "to_on": TODAY + DAY,
        "reason": "đi chơi",
        "sent_at": timezone.now(),
    }
    # The app role has no grant on these columns; the trigger holds them for the owner too.
    for column, value in edits.items():
        with pytest.raises(ProgrammingError, match="permission denied"):
            change(a, pk, **{column: value})
        with owner_role():
            refused(
                "leaverequest_lifecycle",
                a,
                lambda column=column, value=value: touch(
                    pk, **{column: value}, status=Status.CANCELLED
                ),
            )
    with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
        LeaveRequest.objects.filter(pk=pk).delete()


def test_a_request_is_audited_when_sent_and_when_decided(schools, class_7a, parents):
    a, _ = schools
    pk = leave(a, parents["an_mother"], class_7a["an"]).pk
    change(a, pk, status=Status.CANCELLED)
    insert, update = audited(a)
    assert (insert.action, insert.target_id, insert.details["status"]) == ("insert", pk, "waiting")
    assert (update.action, update.target_id) == ("update", pk)
    assert update.details["status"] == ["waiting", "cancelled"]


# --- the API --------------------------------------------------------------------------------


def send(client, student, from_on=TODAY, to_on=None, reason="Con ốm"):
    body = {"student": student.pk, "from_on": str(from_on), "to_on": str(to_on or from_on)}
    return client.post(
        LEAVE_URL, {**body, "reason": reason}, content_type="application/json", HTTP_HOST=A
    )


def act(client, pk, action, **body):
    return client.post(
        f"{LEAVE_URL}{pk}/{action}/", body, content_type="application/json", HTTP_HOST=A
    )


def listed(client, **query):
    response = client.get(LEAVE_URL, query, HTTP_HOST=A)
    assert response.status_code == 200, response.json()
    return [r["id"] for r in response.json()]


def test_a_guardian_sends_a_request_for_their_child_and_it_waits(schools, class_7a, parents):
    a, _ = schools
    client = sign_in(A, "0912000002")
    response = send(client, class_7a["an"], TODAY + DAY, TODAY + 2 * DAY)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert {k: body[k] for k in ("student_name", "class_name", "sent_by_name", "status")} == {
        "student_name": "An",
        "class_name": "7A",
        "sent_by_name": "Guardian 2",
        "status": "waiting",
    }
    assert (body["from_on"], body["to_on"], body["reason"]) == (
        str(TODAY + DAY),
        str(TODAY + 2 * DAY),
        "Con ốm",
    )
    assert (body["decided_by"], body["decided_by_name"], body["decided_at"]) == (None, None, None)
    (event,) = audited(a)
    assert (event.action, event.target_id, event.actor_membership_id) == (
        "insert",
        body["id"],
        parents["an_mother"].pk,
    )
    # Today itself is allowed, the longest stay is 30 days, and the two ends may be the same day.
    assert send(client, class_7a["an"], TODAY + WEEK, TODAY + WEEK + 29 * DAY).status_code == 201


def test_only_a_guardian_of_the_student_sends_a_request_for_them(
    schools, admin_a, class_7a, parents
):
    a, _ = schools
    an, binh = class_7a["an"], class_7a["binh"]
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    # A Guardian of another student, then everyone who is no Guardian: refused, nothing stored.
    for who in ("0912000004", "alice@example.com", "t1@example.com", "board@example.com"):
        assert send(sign_in(A, who), an).status_code == 403
    assert send(sign_in(A, "admin-a@example.com"), an).status_code == 403
    mother = sign_in(A, "0912000002")
    assert send(mother, binh).status_code == 403
    gone = mother.post(
        LEAVE_URL,
        {"student": 0, "from_on": str(TODAY), "to_on": str(TODAY), "reason": "x"},
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert gone.status_code == 403  # a student that is not there reads as one that is not theirs
    nameless = mother.post(LEAVE_URL, {"reason": "x"}, content_type="application/json", HTTP_HOST=A)
    assert (nameless.status_code, nameless.json()) == (400, {"student": ["required"]})
    with school_scope(a.pk):
        assert not LeaveRequest.objects.exists()
    assert send(mother, an).status_code == 201


def test_a_request_starts_today_or_later_and_the_student_is_enrolled_that_day(
    schools, class_7a, parents
):
    a, _ = schools
    mother = sign_in(A, "0912000002")
    an = class_7a["an"]

    def refusal(response):
        assert response.status_code == 400, response.json()
        return response.json()

    assert refusal(send(mother, an, TODAY - DAY)) == {"from_on": ["in_the_past"]}
    assert refusal(send(mother, an, TODAY + DAY, TODAY)) == {"to_on": ["before_from_on"]}
    assert refusal(send(mother, an, TODAY, TODAY + 30 * DAY)) == {"to_on": ["range_too_long"]}
    assert refusal(send(mother, an, reason="")) == {"reason": ["This field may not be blank."]}
    # An's enrollment ends with the year: the day after it, he is in no class.
    after_year = class_7a["year"].ends_on + DAY
    assert refusal(send(mother, an, after_year)) == {"from_on": ["not_enrolled"]}
    with school_scope(a.pk):
        assert not LeaveRequest.objects.exists()


def test_a_request_over_a_waiting_or_approved_one_is_refused_a_declined_one_frees_the_days(
    schools, class_7a, parents
):
    mother, father = sign_in(A, "0912000002"), sign_in(A, "0912000003")
    homeroom, an = sign_in(A, "alice@example.com"), class_7a["an"]
    first = send(mother, an, TODAY, TODAY + 2 * DAY).json()["id"]
    # The other parent's request over the same days is refused as well: it is the student's day.
    over = send(father, an, TODAY + 2 * DAY, TODAY + 3 * DAY)
    assert (over.status_code, over.json()) == (400, {"constraint": ["leaverequest_no_overlap"]})
    assert act(homeroom, first, "approve").status_code == 200
    assert send(father, an, TODAY + 2 * DAY).status_code == 400
    assert send(father, an, TODAY + 3 * DAY).status_code == 201  # the next day is free
    second = send(mother, an, TODAY + 10 * DAY).json()["id"]
    assert act(homeroom, second, "decline", comment="không").status_code == 200
    assert send(father, an, TODAY + 10 * DAY).status_code == 201
    third = send(mother, an, TODAY + 20 * DAY).json()["id"]
    assert act(mother, third, "cancel").status_code == 200
    assert send(father, an, TODAY + 20 * DAY).status_code == 201


def test_the_homeroom_teacher_of_the_class_and_the_board_decide(
    schools, admin_a, class_7a, parents
):
    a, _ = schools
    homeroom_of_7b(a, class_7a, "h7b@example.com")
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    mother, binh_mother = sign_in(A, "0912000002"), sign_in(A, "0912000004")
    an_request = send(mother, class_7a["an"]).json()["id"]
    binh_request = send(binh_mother, class_7a["binh"]).json()["id"]
    # Anyone else is refused, for approving and for declining: the other class's homeroom
    # teacher, a subject teacher, the School admin and the Guardians themselves.
    for who in ("h7b@example.com", "t1@example.com", "admin-a@example.com", "0912000002"):
        client = sign_in(A, who)
        assert act(client, an_request, "approve").status_code == 403
        assert act(client, an_request, "decline", comment="không").status_code == 403
    assert act(mother, binh_request, "approve").status_code == 403
    assert act(sign_in(A, "alice@example.com"), binh_request, "approve").status_code == 403
    assert act(sign_in(A, "alice@example.com"), 0, "approve").status_code == 404
    with school_scope(a.pk):
        assert set(LeaveRequest.objects.values_list("status", flat=True)) == {"waiting"}

    # The homeroom teacher of 7A approves An's request with no comment; the board declines
    # Binh's with one.
    approved = act(sign_in(A, "alice@example.com"), an_request, "approve")
    assert approved.status_code == 200, approved.json()
    assert {k: approved.json()[k] for k in ("status", "decided_by_name", "decision_comment")} == {
        "status": "approved",
        "decided_by_name": "Alice",
        "decision_comment": "",
    }
    assert approved.json()["decided_at"] is not None
    declined = act(
        sign_in(A, "board@example.com"), binh_request, "decline", comment="Đã nghỉ nhiều"
    )
    assert declined.status_code == 200, declined.json()
    assert (declined.json()["status"], declined.json()["decision_comment"]) == (
        "declined",
        "Đã nghỉ nhiều",
    )
    update = [e for e in audited(a) if e.action == "update"]
    assert [(e.target_id, e.details["status"][1]) for e in update] == [
        (an_request, "approved"),
        (binh_request, "declined"),
    ]
    with school_scope(a.pk):
        alice = Membership.objects.get(account__email="alice@example.com")
    assert update[0].actor_membership_id == alice.pk


def test_declining_needs_a_comment_and_a_request_is_decided_once(schools, class_7a, parents):
    a, _ = schools
    mother, homeroom = sign_in(A, "0912000002"), sign_in(A, "alice@example.com")
    pk = send(mother, class_7a["an"]).json()["id"]
    for body in ({}, {"comment": ""}, {"comment": "   "}):
        refusal = act(homeroom, pk, "decline", **body)
        assert (refusal.status_code, list(refusal.json())) == (400, ["comment"])
    too_long = act(homeroom, pk, "decline", comment="x" * 501)
    assert too_long.status_code == 400
    assert act(homeroom, pk, "decline", comment="không").status_code == 200
    # Decided: nothing changes it again, whoever asks.
    for action, body in (("approve", {}), ("decline", {"comment": "lại"}), ("cancel", {})):
        again = act(mother if action == "cancel" else homeroom, pk, action, **body)
        assert (again.status_code, again.json()) == (400, {"status": ["not_waiting"]})
    approved = send(mother, class_7a["an"], TODAY + WEEK).json()["id"]
    assert act(homeroom, approved, "approve", comment="ok").status_code == 200
    assert act(homeroom, approved, "decline", comment="không").status_code == 400
    assert act(mother, approved, "cancel").json() == {"status": ["not_waiting"]}


def test_only_the_sender_cancels_and_only_while_waiting(schools, class_7a, parents):
    a, _ = schools
    mother, father = sign_in(A, "0912000002"), sign_in(A, "0912000003")
    homeroom = sign_in(A, "alice@example.com")
    pk = send(mother, class_7a["an"]).json()["id"]
    # The other parent of the child, another child's parent, the homeroom teacher: refused.
    for client in (father, sign_in(A, "0912000004"), homeroom, sign_in(A, "t1@example.com")):
        assert act(client, pk, "cancel").status_code == 403
    assert act(mother, 0, "cancel").status_code == 404
    cancelled = act(mother, pk, "cancel")
    assert cancelled.status_code == 200, cancelled.json()
    assert cancelled.json()["status"] == "cancelled"
    assert (cancelled.json()["decided_by"], cancelled.json()["decided_at"]) == (None, None)
    assert act(homeroom, pk, "approve").status_code == 400  # cancelled is final
    assert [e.details["status"][1] for e in audited(a) if e.action == "update"] == ["cancelled"]


def test_each_role_lists_the_requests_it_may_see_newest_first(schools, admin_a, class_7a, parents):
    a, _ = schools
    homeroom_of_7b(a, class_7a, "h7b@example.com")
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    mother, father = sign_in(A, "0912000002"), sign_in(A, "0912000003")
    binh_mother = sign_in(A, "0912000004")
    first = send(mother, class_7a["an"], TODAY).json()["id"]
    second = send(mother, class_7a["an"], TODAY + WEEK).json()["id"]
    binh = send(binh_mother, class_7a["binh"], TODAY).json()["id"]
    assert act(sign_in(A, "alice@example.com"), first, "approve").status_code == 200

    # A Guardian: what they sent, for their own child (the other parent sees none of it).
    assert listed(mother) == [second, first]
    assert listed(father) == []
    assert listed(binh_mother) == [binh]
    # The homeroom teacher: their class's students' requests; the board: all.
    assert listed(sign_in(A, "alice@example.com")) == [second, first]
    assert listed(sign_in(A, "h7b@example.com")) == [binh]
    assert listed(sign_in(A, "board@example.com")) == [binh, second, first]
    # No role in a class, a subject teacher and the School admin: an empty list, not a refusal.
    for who in ("t1@example.com", "admin-a@example.com"):
        assert listed(sign_in(A, who)) == []
    # The filters.
    board = sign_in(A, "board@example.com")
    assert listed(board, status="waiting") == [binh, second]
    assert listed(board, status="approved") == [first]
    assert listed(board, student=class_7a["an"].pk) == [second, first]
    assert listed(board, student="x") == []
    unknown = board.get(LEAVE_URL, {"status": "lost"}, HTTP_HOST=A)
    assert (unknown.status_code, unknown.json()) == (400, {"status": ["unknown"]})
    row = mother.get(LEAVE_URL, HTTP_HOST=A).json()[1]
    assert (row["student_name"], row["class_name"], row["decided_by_name"]) == ("An", "7A", "Alice")


def test_a_guardian_who_is_no_longer_linked_sees_and_sends_nothing(schools, class_7a, parents):
    a, _ = schools
    mother = sign_in(A, "0912000002")
    pk = send(mother, class_7a["an"]).json()["id"]
    with school_scope(a.pk):
        GuardianLink.objects.filter(membership=parents["an_mother"]).update(valid_to=TODAY - DAY)
    assert listed(mother) == []
    assert send(mother, class_7a["an"], TODAY + WEEK).status_code == 403
    assert act(mother, pk, "cancel").status_code == 403


def test_the_children_a_guardian_may_send_for_are_listed_by_name(schools, class_7a, parents):
    a, _ = schools
    with school_scope(a.pk):  # a second child of the mother's, in 7B
        GuardianLink.objects.create(
            school=a,
            membership=parents["an_mother"],
            student=class_7a["binh"],
            relation="mother",
            valid_from=TODAY - DAY,
        )
    children = sign_in(A, "0912000002").get(f"{LEAVE_URL}children/", HTTP_HOST=A).json()
    assert children == [
        {"id": class_7a["an"].pk, "name": "An", "class_name": "7A"},
        {"id": class_7a["binh"].pk, "name": "Binh", "class_name": "7B"},
    ]
    assert sign_in(A, "alice@example.com").get(f"{LEAVE_URL}children/", HTTP_HOST=A).json() == []


def approved_leave(school, world, sender, student, from_on, to_on):
    return leave(
        school,
        sender,
        student,
        from_on,
        to_on,
        status=Status.APPROVED,
        decided_by=world["t1"],
        decided_at=timezone.now(),
    )


def test_the_sheet_flags_an_approved_leave_and_writes_no_mark(schools, class_7a, parents):
    a, _ = schools
    mother, an, bao, dung = parents["an_mother"], class_7a["an"], class_7a["bao"], class_7a["dung"]
    approved = approved_leave(a, class_7a, mother, an, TODAY - DAY, TODAY + DAY)
    # Waiting and cancelled requests and an approved one for other days do not count.
    leave(a, mother, bao)
    leave(a, mother, dung, status=Status.CANCELLED)
    approved_leave(a, class_7a, mother, bao, TODAY + 3 * DAY, TODAY + 4 * DAY)
    t1 = sign_in(A, "t1@example.com")

    def leaves():
        students = t1.get(sheet_url(class_7a), HTTP_HOST=A).json()["students"]
        return {s["name"]: (s["leave"], s["mark"]) for s in students}

    assert leaves() == {
        "An": ({"id": approved.pk, "from_on": str(TODAY - DAY), "to_on": str(TODAY + DAY)}, None),
        "Bao": (None, None),
        "Dung": (None, None),
    }
    assert stored(a) == {}  # asking for the sheet marks nobody
    # A taken sheet keeps its marks, the flag beside them; so does a request approved after it.
    assert put(t1, class_7a, sheet(an, bao, dung, An="late")).status_code == 200
    later = approved_leave(a, class_7a, mother, dung, TODAY, TODAY)
    taken = leaves()
    assert taken["An"] == (
        {"id": approved.pk, "from_on": str(TODAY - DAY), "to_on": str(TODAY + DAY)},
        {"status": "late", "note": ""},
    )
    assert taken["Bao"] == (None, {"status": "present", "note": ""})
    assert taken["Dung"] == (
        {"id": later.pk, "from_on": str(TODAY), "to_on": str(TODAY)},
        {"status": "present", "note": ""},
    )
