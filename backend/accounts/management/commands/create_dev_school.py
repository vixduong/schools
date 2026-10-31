from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Account, Membership, RoleAssignment
from tenancy.models import School
from tenancy.rls import school_scope


class Command(BaseCommand):
    help = (
        "DEV ONLY: create (or reuse) a School, an Account and its active school_admin "
        "Membership. Refuses to run unless DJANGO_DEBUG=1. Run with DB_ROLE=owner."
    )

    def add_arguments(self, parser):
        parser.add_argument("subdomain")
        parser.add_argument("email")
        parser.add_argument("--password", default="dev-password")
        parser.add_argument("--name", help="School name (default: the subdomain)")

    def handle(self, *args, subdomain, email, password, name, **options):
        if not settings.DEBUG:
            raise CommandError("create_dev_school is for development only (DJANGO_DEBUG=1).")
        school, _ = School.objects.get_or_create(
            subdomain=subdomain, defaults={"name": name or subdomain}
        )
        try:
            account = Account.objects.get_by_identifier(email)
        except Account.DoesNotExist:
            account = Account(email=email, display_name=email)
            account.set_password(password)
            account.save()
        with school_scope(school.pk):
            membership, _ = Membership.objects.get_or_create(school=school, account=account)
            RoleAssignment.objects.get_or_create(
                school=school,
                membership=membership,
                role=RoleAssignment.Role.SCHOOL_ADMIN,
                scope_kind=None,
                scope_id=None,
                school_year="dev",
                defaults={"valid_from": date.today()},
            )
        self.stdout.write(
            f"{subdomain}.{settings.BASE_DOMAIN}: sign in as {account.email} "
            f"(password set only when the Account was created)"
        )
