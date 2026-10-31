from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Account, Membership, RoleAssignment
from schools.models import SchoolYear
from tenancy.models import School
from tenancy.rls import school_scope


class Command(BaseCommand):
    help = (
        "DEV ONLY: create (or reuse) a School, its current SchoolYear, an Account and its "
        "active school_admin Membership. Refuses to run unless DJANGO_DEBUG=1. "
        "Run with DB_ROLE=owner."
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
            # Vietnamese school years run September to August.
            today = date.today()
            start = today.year if today.month >= 9 else today.year - 1
            year, _ = SchoolYear.objects.get_or_create(
                school=school,
                name=f"{start}-{start + 1}",
                defaults={"starts_on": date(start, 9, 1), "ends_on": date(start + 1, 8, 31)},
            )
            RoleAssignment.objects.get_or_create(
                school=school,
                membership=membership,
                role=RoleAssignment.Role.SCHOOL_ADMIN,
                school_year=year,
                defaults={"valid_from": year.starts_on},
            )
        self.stdout.write(
            f"{subdomain}.{settings.BASE_DOMAIN}: sign in as {account.email} "
            f"(password set only when the Account was created)"
        )
