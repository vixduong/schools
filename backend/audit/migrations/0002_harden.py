from datetime import timedelta

from django.conf import settings
from django.db import migrations, models

APP = settings.APP_DB_USER
PATH = "pg_catalog, public, pg_temp"

UP = f"""
-- pg_temp last: a temp table can no longer shadow audit_auditevent inside the definer functions.
ALTER FUNCTION audit_row_change() SET search_path = {PATH};
CREATE OR REPLACE FUNCTION audit_record(action text, target_table text, target_id bigint,
                                        details jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = {PATH} AS $$
BEGIN
    -- Row changes come only from the trigger; app events are named "<area>.<what>".
    IF position('.' IN action) = 0 THEN
        RAISE EXCEPTION 'audit_record: % is not an event name', action;
    END IF;
    INSERT INTO public.audit_auditevent
        (school_id, at, actor_membership_id, actor, action, target_table, target_id, details)
    VALUES (NULLIF(current_setting('app.school_id', true), '')::bigint, now(),
            NULLIF(current_setting('app.membership_id', true), '')::bigint,
            COALESCE(NULLIF(current_setting('app.actor', true), ''), 'system'),
            action, COALESCE(target_table, ''), target_id, COALESCE(details, '{{}}'));
END $$;
-- No temp objects for anyone but those granted explicitly (none): closes the shadowing route.
DO $$ BEGIN
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END $$;
-- A grant only gets revoked after creation.
REVOKE UPDATE ON audit_supportgrant FROM {APP};
GRANT UPDATE (revoked_at, revoked_by_id) ON audit_supportgrant TO {APP};
"""
DOWN = f"""
REVOKE UPDATE (revoked_at, revoked_by_id) ON audit_supportgrant FROM {APP};
GRANT UPDATE ON audit_supportgrant TO {APP};
DO $$ BEGIN
    EXECUTE format('GRANT TEMPORARY ON DATABASE %I TO PUBLIC', current_database());
END $$;
ALTER FUNCTION audit_row_change() SET search_path = public;
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        migrations.AddConstraint(
            model_name="supportgrant",
            constraint=models.CheckConstraint(
                condition=models.Q(ends_at__lte=models.F("starts_at") + timedelta(hours=72)),
                name="supportgrant_at_most_72_hours",
            ),
        ),
        migrations.RunSQL(UP, DOWN),
    ]
