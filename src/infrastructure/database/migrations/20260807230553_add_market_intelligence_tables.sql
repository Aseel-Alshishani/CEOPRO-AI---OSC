"""
Shared, tenant-safe database connection helper for src/ai/.

Every query already filters WHERE tenant_id = %s explicitly, but Postgres's
real safety net -- Row-Level Security -- only works when (a) the connecting
role is not a superuser (see migration *_add_app_role_and_force_rls.sql) and
(b) app.current_tenant_id is set on the session per the RLS policies in
init_schema.sql. Use get_tenant_connection(tenant_id) here instead of calling
psycopg2.connect(...) directly anywhere in src/ai/.
"""
import os
import psycopg2


def get_tenant_connection(tenant_id: str):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SET app.current_tenant_id = %s;", (str(tenant_id),))
    conn.commit()
    return conn
