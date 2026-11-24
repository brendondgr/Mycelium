"""EXP-2026-11-028: prove the sandbox holds only the fictional demo world and
the public corpus, before any model turn.

    <container, -e SANDBOX_DB=mycelium_sandbox_exp028> python …/code/check_sandbox.py

Connects through ``sandbox.collab.bootstrap`` (which rewrites the database
name and stops unless Django really is on it), then counts every kind of row
that must not be there. Prints one JSON object; exit code 1 if any count in
``must_be_zero`` is not zero. ``present`` lists what is there, for the record.

``counts()`` is also imported by ``run_arms.py``, which refuses to start
unless every count is zero. Chat threads made by this experiment's own turns
(``demo_visitor = 'EXP-2026-11-028'``) are allowed; any other thread is not.
"""

from __future__ import annotations

import json
import sys

VISITOR = "EXP-2026-11-028"


def counts() -> dict:
    from django.db import connection

    from apps.demo.world import DOMAIN

    def one(sql, params=None):
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchone()[0]

    def tables(prefix):
        with connection.cursor() as cur:
            cur.execute("select table_name from information_schema.tables where table_schema='public' "
                        "and table_name like %s order by 1", [prefix + r"\_%"])
            return [r[0] for r in cur.fetchall()]

    like = "%@" + DOMAIN
    du = "(select id from auth_user where email ilike %s)"
    lab = "(select lab_id from demo_demoworld where key='default')"
    dept = "(select department_id from demo_demoworld where key='default')"
    proj = f"(select id from research_project where scope_lab_id = {lab})"
    zero = {
        "accounts_outside_the_demo_domain": one("select count(*) from auth_user where email not ilike %s", [like]),
        "labs_other_than_the_demo_lab": one(f"select count(*) from accounts_lab where id is distinct from {lab}"),
        "departments_other_than_the_demo_department":
            one(f"select count(*) from accounts_department where id is distinct from {dept}"),
        "projects_outside_the_demo_lab":
            one(f"select count(*) from research_project where scope_lab_id is distinct from {lab}"),
        "chat_threads_not_made_by_this_experiment":
            one("select count(*) from agent_agentthread where demo_visitor is distinct from %s", [VISITOR]),
        "chat_threads_of_a_non_demo_account":
            one(f"select count(*) from agent_agentthread where user_id not in {du}", [like]),
        "ambient_rows_all_tables": sum(one(f'select count(*) from "{t}"') for t in tables("ambient")),
        "integration_rows_all_tables": sum(one(f'select count(*) from "{t}"') for t in tables("integrations")),
        "rankings_for_a_non_demo_target": one(
            f"select count(*) from content_relevancescore where not (coalesce(target_user_id in {du}, false) "
            f"or coalesce(target_lab_id = {lab}, false) or coalesce(target_department_id = {dept}, false) "
            f"or coalesce(target_project_id in {proj}, false))", [like]),
        "knowledge_edges_for_a_non_demo_owner": one(
            f"select count(*) from knowledge_edge where not (coalesce(user_id in {du}, false) "
            f"or coalesce(lab_id = {lab}, false) or coalesce(project_id in {proj}, false))", [like]),
        "concepts_scoped_to_a_non_demo_owner": one(
            f"select count(*) from knowledge_concept where (scope_user_id is not null and scope_user_id not in {du}) "
            f"or scope_lab_id is distinct from null and scope_lab_id <> {lab} "
            f"or scope_department_id is distinct from null and scope_department_id <> {dept}", [like]),
        "author_works_and_coauthorships": one("select count(*) from accounts_authorwork")
            + one("select count(*) from knowledge_coauthorship"),
        "collaboration_settings": one("select count(*) from collab_collaborationsetting"),
        "sessions_invitations_and_email_verifications": one("select count(*) from django_session")
            + one("select count(*) from accounts_labinvitation") + one("select count(*) from accounts_emailverification"),
    }
    present = {
        "database": connection.settings_dict["NAME"],
        "demo_accounts": one("select count(*) from auth_user where email ilike %s", [like]),
        "labs": one("select count(*) from accounts_lab"),
        "departments": one("select count(*) from accounts_department"),
        "projects": one("select count(*) from research_project"),
        "corpus_items": one("select count(*) from content_contentitem"),
        "rankings": one("select count(*) from content_relevancescore"),
        "threads_of_this_experiment":
            one("select count(*) from agent_agentthread where demo_visitor = %s", [VISITOR]),
    }
    return {"must_be_zero": zero, "present": present, "ok": not any(zero.values())}


def main() -> int:
    sys.path[:0] = ["/app/web/backend", "/app"]
    from sandbox.collab import bootstrap

    bootstrap.setup()
    doc = counts()
    print(json.dumps(doc, indent=1))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
