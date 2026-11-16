import logging

from django.core.mail import EmailMessage
from django.db.models import Q
from django.utils import timezone
from django_tasks import task

from tenancy.rls import school_scope

from .models import Notice, NoticeRecipient

logger = logging.getLogger(__name__)

BATCH = 50


class NoticeEmailFailed(Exception):
    """Some recipients were not emailed. The message holds counts only: the worker stores the
    exception text and traceback in a table without RLS, and an SMTP error carries the address."""


@task()
def email_notice(school_id: int, notice_id: int) -> None:
    """Email a notice to its recipients that have an Account email and no `emailed_at`, one
    message each, in batches of `BATCH` paged by id (a recipient whose send fails is not picked
    again, so failures cannot loop). Reading a batch and stamping the sent ones are two short
    School scopes; the mail goes out between them, outside any transaction (SMTP is slow). A
    re-run sends only the unstamped. Logs ids and counts, never an address or text."""
    last_id = failed = total = 0
    while True:
        with school_scope(school_id):
            notice = Notice.objects.select_related("school", "sender__account").get(pk=notice_id)
            batch = list(
                NoticeRecipient.objects.filter(
                    ~Q(membership__account__email__isnull=True),
                    ~Q(membership__account__email=""),
                    notice=notice,
                    emailed_at__isnull=True,
                    id__gt=last_id,
                )
                .select_related("membership__account")
                .order_by("id")[:BATCH]
            )
        if not batch:
            break
        last_id = batch[-1].pk
        text = f"{notice.body}\n\n{notice.sender.account.display_name}\n{notice.school.name}"
        sent = []
        for recipient in batch:
            # shortcut: one SMTP session per message; share one per batch if the provider limits.
            message = EmailMessage(notice.title, text, to=[recipient.membership.account.email])
            try:
                message.send()
            except Exception as error:
                logger.warning(
                    "notice %s: email to recipient %s failed (%s)",
                    notice_id,
                    recipient.pk,
                    type(error).__name__,
                )
                failed += 1
            else:
                sent.append(recipient.pk)
        total += len(batch)
        with school_scope(school_id):
            NoticeRecipient.objects.filter(pk__in=sent, emailed_at__isnull=True).update(
                emailed_at=timezone.now()
            )
    logger.info("notice %s: %s emails attempted, %s failed", notice_id, total, failed)
    if failed:
        raise NoticeEmailFailed(f"{failed} of {total} notice emails failed") from None
