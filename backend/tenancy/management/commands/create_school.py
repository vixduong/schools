"""The operator's way to open a School (docs/slices/slice-9.md): the School and an invitation for
its first School admin. No Account is created (ADR 0002): the person activates the code."""

import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.invitations import issue_code
from accounts.models import Invitation, InvitationRole, RoleAssignment
from accounts.serializers import IdentifierField
from tenancy.models import SUBDOMAIN_PATTERN, School
from tenancy.rls import school_scope, set_actor

RESERVED = {"www", "api", "app", "admin", "mail", "static", "status"}


class Command(BaseCommand):
    help = (
        "Create a School and an invitation for its first School admin, and print the code. Run "
        "again before anyone has activated it to issue a fresh code. Run with DB_ROLE=owner."
    )

    def add_arguments(self, parser):
        parser.add_argument("subdomain", help="One DNS label: <subdomain>.<BASE_DOMAIN>")
        parser.add_argument("--name", required=True, help="The School's name")
        parser.add_argument("--admin", required=True, help="The admin's email or VN mobile")
        parser.add_argument("--admin-name", required=True, help="The admin's name")
        parser.add_argument("--operator", required=True, help="Your name, for the School's log")

    def handle(self, *args, subdomain, name, admin, admin_name, operator, **options):
        if not re.fullmatch(SUBDOMAIN_PATTERN, subdomain) or subdomain in RESERVED:
            raise CommandError(f"{subdomain!r} is not a usable subdomain (one lower-case label).")
        try:
            identifier = IdentifierField().run_validation(admin)
        except ValidationError:
            raise CommandError(f"{admin!r} is neither an email nor a VN mobile number.") from None
        school, created = School.objects.get_or_create(subdomain=subdomain, defaults={"name": name})
        with school_scope(school.pk):
            set_actor(f"operator:{operator}")
            has_admin = (
                RoleAssignment.objects.in_force()
                .filter(role=RoleAssignment.Role.SCHOOL_ADMIN, status=RoleAssignment.Status.ACTIVE)
                .exists()
            )
            if has_admin:
                raise CommandError(
                    f"{subdomain} already has a School admin: they invite everyone else."
                )
            # A lost or expired code: the earlier operator invitations stop working.
            Invitation.objects.filter(
                created_by__isnull=True, status=Invitation.Status.PENDING
            ).update(status=Invitation.Status.REVOKED)
            invitation = Invitation(
                school=school,
                kind=Invitation.Kind.STAFF,
                identifier=identifier,
                display_name=admin_name,
            )
            code = issue_code(invitation)
            with transaction.atomic():
                invitation.save()
                InvitationRole.objects.create(
                    school=school,
                    invitation=invitation,
                    role=RoleAssignment.Role.SCHOOL_ADMIN,
                    valid_from=timezone.localdate(),
                )
        scheme = "https" if settings.SECURE_COOKIES else "http"
        self.stdout.write(
            f"{'Created' if created else 'Existing'} School {school.name!r}.\n"
            f"First School admin: {admin_name} ({identifier})\n"
            f"Activate at {scheme}://{subdomain}.{settings.BASE_DOMAIN}/activate\n"
            f"Code (shown once, valid until {invitation.expires_at:%d/%m/%Y}): {code}\n"
        )
