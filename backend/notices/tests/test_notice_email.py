"""The email of a notice: the task, its batches and failures, the send view's enqueue after the
commit, and a run of the real worker (as the app role, on the task table's narrow grant)."""

import smtplib

import pytest
from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.db import connection
from django_tasks.base import TaskResultStatus
from django_tasks_db.models import DBTaskResult

import notices.tasks as tasks
from accounts.models import Account, Membership
from notices.models import Notice, NoticeRecipient
from notices.tasks import NoticeEmailFailed, email_notice
from schools.models import GuardianLink
from schools.tests.factories import make_class
from tenancy.rls import school_scope
from testing import A, make_account, owner_role, sign_in

from .conftest import DAY, TODAY, Role, assign
from .test_notice_rules import send

Audience = Notice.Audience


def homeroom_notice(world, **fields):
    with school_scope(world["school"].pk):
        return send(world, "hr_7a", Audience.HOMEROOM_GUARDIANS, "7A", **fields)


def stamped(world, notice):
    """Recipient email -> whether it has an emailed_at."""
    with school_scope(world["school"].pk):
        rows = NoticeRecipient.objects.filter(notice=notice).select_related("membership__account")
        return {r.membership.account.email: r.emailed_at is not None for r in rows}


def run_task(world, notice):
    return email_notice.func(school_id=world["school"].pk, notice_id=notice.pk)


def refuse(monkeypatch, addresses=None):
    """Sending to `addresses` (all when None) raises as an SMTP server refusing them would, with
    the address in the exception."""
    real = EmailMessage.send

    def send_or_refuse(self, fail_silently=False):
        if addresses is None or set(self.to) & set(addresses):
            raise smtplib.SMTPRecipientsRefused({self.to[0]: (550, b"mailbox unavailable")})
        return real(self, fail_silently)

    monkeypatch.setattr(EmailMessage, "send", send_or_refuse)


def test_each_recipient_gets_the_title_as_subject_and_the_text_signed_by_sender_and_school(world):
    notice = homeroom_notice(world, title="Họp phụ huynh", body="Thứ Bảy, 8 giờ.")
    run_task(world, notice)
    assert sorted(m.to[0] for m in mail.outbox) == ["g_an@example.com", "g_chi@example.com"]
    message = mail.outbox[0]
    assert message.subject == "Họp phụ huynh" and len(message.to) == 1
    assert message.body == "Thứ Bảy, 8 giờ.\n\nHr 7A\nA"
    assert stamped(world, notice) == {"g_an@example.com": True, "g_chi@example.com": True}


def test_a_recipient_without_an_email_is_skipped_and_left_unstamped(world):
    a = world["school"]
    account = make_account(None, "0912345678", "Phone only")
    with school_scope(a.pk):
        membership = Membership.objects.create(school=a, account=account)
        GuardianLink.objects.create(
            school=a,
            membership=membership,
            student=world["students"]["an"],
            relation="father",
            valid_from=TODAY - 30 * DAY,
        )
    notice = homeroom_notice(world)
    assert run_task(world, notice) is None
    assert len(mail.outbox) == 2
    with school_scope(a.pk):
        assert NoticeRecipient.objects.get(notice=notice, membership=membership).emailed_at is None


def test_a_failing_recipient_stays_unstamped_the_rest_are_sent_and_a_rerun_sends_only_it(
    world, monkeypatch
):
    notice = homeroom_notice(world)
    with monkeypatch.context() as patch:
        refuse(patch, ["g_an@example.com"])
        with pytest.raises(NoticeEmailFailed) as failure:
            run_task(world, notice)
    assert [m.to[0] for m in mail.outbox] == ["g_chi@example.com"]
    assert stamped(world, notice) == {"g_an@example.com": False, "g_chi@example.com": True}
    # The failure names counts, never an address: the worker stores it in a table without RLS.
    assert str(failure.value) == "1 of 2 notice emails failed"
    assert failure.value.__cause__ is None and failure.value.__suppress_context__
    assert run_task(world, notice) is None
    assert [m.to[0] for m in mail.outbox] == ["g_chi@example.com", "g_an@example.com"]
    assert stamped(world, notice) == {"g_an@example.com": True, "g_chi@example.com": True}
    run_task(world, notice)
    assert len(mail.outbox) == 2  # nothing left to send


def test_more_than_one_batch_of_failing_recipients_ends_the_loop(world, monkeypatch):
    a = world["school"]
    count = tasks.BATCH + 5
    with owner_role():
        Account.objects.bulk_create(
            Account(email=f"p{n}@example.com", display_name=f"P{n}") for n in range(count)
        )
    with school_scope(a.pk):
        accounts = Account.objects.filter(email__startswith="p", email__endswith="@example.com")
        memberships = Membership.objects.bulk_create(
            Membership(school=a, account=account) for account in accounts
        )
        GuardianLink.objects.bulk_create(
            GuardianLink(
                school=a,
                membership=m,
                student=world["students"]["an"],
                relation="other",
                valid_from=TODAY - 30 * DAY,
            )
            for m in memberships
        )
    notice = homeroom_notice(world)
    attempts = []

    def count_and_refuse(self, fail_silently=False):
        attempts.append(self.to[0])
        raise smtplib.SMTPRecipientsRefused({self.to[0]: (550, b"no")})

    monkeypatch.setattr(EmailMessage, "send", count_and_refuse)
    with pytest.raises(NoticeEmailFailed, match=f"{count + 2} of {count + 2} notice emails"):
        run_task(world, notice)
    assert len(attempts) == count + 2 and len(set(attempts)) == count + 2  # each tried once
    assert not any(stamped(world, notice).values())


def test_a_notice_without_recipients_to_email_sends_nothing(world):
    with school_scope(world["school"].pk):
        notice = send(world, "t_lit", Audience.CLASS, "7B")  # g_binh and s_binh
    run_task(world, notice)
    assert sorted(m.to[0] for m in mail.outbox) == ["g_binh@example.com", "s_binh@example.com"]


# --- the send view -----------------------------------------------------------------------------


def post_notice(name="hr_7a", **fields):
    body = {
        "audience": "homeroom_guardians",
        "title": "Tiêu đề",
        "body": "Nội dung",
        "school_class": fields.pop("school_class"),
        **fields,
    }
    return sign_in(A, f"{name}@example.com").post(
        "/api/setup/notices/", body, content_type="application/json", HTTP_HOST=A
    )


@pytest.mark.usefixtures("as_app_role")
class TestSendEnqueuesTheEmail:
    def test_a_committed_send_queues_one_task_carrying_ids_only(self, world):
        response = post_notice(school_class=world["7A"].pk)
        assert response.status_code == 201
        (queued,) = DBTaskResult.objects.all()
        assert queued.task_path == "notices.tasks.email_notice"
        assert queued.args_kwargs == {
            "args": [],
            "kwargs": {"school_id": world["school"].pk, "notice_id": response.json()["id"]},
        }
        assert "Tiêu đề" not in str(queued.args_kwargs) and "@" not in str(queued.args_kwargs)

    def test_a_refused_or_rolled_back_send_queues_nothing(self, world):
        with school_scope(world["school"].pk):
            empty = make_class(world["school"], world["7A"].school_year, "7C")
            assign(world["school"], world["m"]["hr_7a"], Role.HOMEROOM_TEACHER, school_class=empty)
        assert post_notice(school_class=empty.pk).status_code == 400  # reaches nobody
        assert post_notice("t_lit", school_class=world["7A"].pk).status_code == 403
        assert DBTaskResult.objects.count() == 0 and mail.outbox == []

    def test_an_enqueue_that_fails_does_not_undo_a_committed_notice(self, world, monkeypatch):
        class Down:
            @staticmethod
            def enqueue(**kwargs):
                raise ConnectionError("queue down")

        monkeypatch.setattr("notices.views.email_notice", Down)
        response = post_notice(school_class=world["7A"].pk)
        assert response.status_code == 201
        with school_scope(world["school"].pk):
            assert Notice.objects.count() == 1


# --- the real worker ---------------------------------------------------------------------------


def work():
    """One pass of the worker over what is queued (as `manage.py db_worker --batch`)."""
    call_command("db_worker", batch=True, reload=False, startup_delay=False, interval=0)


@pytest.mark.usefixtures("as_app_role")
class TestTheWorker:
    def test_it_runs_the_task_as_the_app_role_and_the_mail_goes_out(self, world):
        assert connection.settings_dict["USER"] == settings.APP_DB_USER
        assert post_notice(school_class=world["7A"].pk).status_code == 201
        assert mail.outbox == []  # queued, not sent by the request
        work()
        assert sorted(m.to[0] for m in mail.outbox) == ["g_an@example.com", "g_chi@example.com"]
        (done,) = DBTaskResult.objects.all()
        assert done.status == TaskResultStatus.SUCCESSFUL

    def test_a_failed_task_row_holds_no_address_or_text(self, world, monkeypatch):
        refuse(monkeypatch)
        assert post_notice(school_class=world["7A"].pk, title="Tiêu đề bí mật").status_code == 201
        work()
        (failed,) = DBTaskResult.objects.all()
        assert failed.status == TaskResultStatus.FAILED
        assert failed.exception_class_path == "notices.tasks.NoticeEmailFailed"
        text = failed.traceback + failed.exception_class_path + str(failed.args_kwargs)
        assert "@" not in text and "bí mật" not in text
        assert "2 of 2 notice emails failed" in failed.traceback
