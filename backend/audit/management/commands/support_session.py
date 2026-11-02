"""The platform operator's only sanctioned way into a School's data (docs/slices/slice-7.md)."""

import code

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from audit.log import record
from audit.models import SupportGrant
from tenancy.models import School
from tenancy.rls import school_scope, set_actor


class Command(BaseCommand):
    help = (
        "Read a School's data as the platform operator while the School has a support grant in "
        "force. Read only; the session and every command go to the School's audit log. Run as "
        "the app role (DB_ROLE=app)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="The School's subdomain")
        parser.add_argument("--operator", required=True, help="Your name, for the School's log")
        parser.add_argument("--command", help="Run this Python and exit (no console)")

    def handle(self, *args, school, operator, command, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            if cursor.fetchone()[0] != settings.APP_DB_USER:
                raise CommandError("Run as the app role (DB_ROLE=app): RLS must apply.")
        found = School.objects.filter(subdomain=school).first()
        if found is None:
            raise CommandError(f"No School {school!r}.")
        session = _Session(found, f"operator:{operator}", self.stdout)
        session.log("support.session_start")
        try:
            if command is not None:
                session.run(command, lambda namespace: exec(command, namespace))
            else:
                _Console(session).interact(banner=f"Support session in {school}, read only.")
        finally:
            session.log("support.session_end", check=False)


class _Session:
    def __init__(self, school, actor, stdout):
        self.school, self.actor, self.stdout = school, actor, stdout
        self.namespace = {"apps": apps, "models": {m.__name__: m for m in apps.get_models()}}

    def log(self, action, details=None, check=True):
        """In its own committed transaction, so the entry stays even if the command fails."""
        with school_scope(self.school.pk):
            grant = SupportGrant.objects.in_force().order_by("-ends_at").first()
            if check and grant is None:
                raise CommandError("No support grant in force for this School.")
            set_actor(self.actor)
            record(action, grant, details)

    def run(self, source, execute):
        self.log("support.command", {"source": source})
        with school_scope(self.school.pk):
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            execute(self.namespace)


class _Console(code.InteractiveConsole):
    """Every complete statement is logged, then run in its own read-only transaction."""

    def __init__(self, session):
        super().__init__(session.namespace)
        self.session = session

    def runsource(self, source, filename="<support>", symbol="single"):
        try:
            compiled = self.compile(source, filename, symbol)
        except (OverflowError, SyntaxError, ValueError):
            self.showsyntaxerror(filename)
            return False
        if compiled is None:
            return True  # incomplete: wait for more lines
        try:
            self.session.run(source, lambda namespace: self.runcode(compiled))
        except CommandError as error:
            self.write(f"{error}\n")
            raise SystemExit(1) from None
        return False
