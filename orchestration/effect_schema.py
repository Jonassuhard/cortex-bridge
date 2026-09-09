"""Staged effect-schema migration, not enabled by the legacy Store.

Call only on an exclusively owned connection after stopping all application
writers. No recovery or dispatch is performed here. Integration must switch
approval consumers together; legacy record_approval is incompatible with v3.
"""
import hashlib
import json
import sqlite3
import time

from .effect_schema_sql import V3_DDL
from .store import _SCHEMA


class MigrationReviewRequired(RuntimeError):
    pass


def _fail():
    raise MigrationReviewRequired("MIGRATION_REVIEW_REQUIRED")


def _statements():
    return [s.strip() for s in V3_DDL.split(";") if s.strip()]


def _table(name):
    return next(s for s in _statements() if s.startswith(f"CREATE TABLE {name} ("))


def _v2_approval():
    sql = _table("approvals")
    sql = sql.replace("  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('mission','local_alias_action')),\n", "")
    sql = sql.replace("  mission_id TEXT REFERENCES missions(id),", "  mission_id TEXT NOT NULL REFERENCES missions(id),")
    sql = sql.replace("  local_action_id TEXT REFERENCES local_alias_actions(action_id),\n", "")
    return sql.split("  CHECK ((owner_kind=")[0].rstrip().removesuffix(",") + "\n)"


def _v2_effect():
    sql = _table("effects").replace(", 'local_alias_action'", "").replace(",'local_alias_action'", "")
    return sql.split(" OR\n         (owner_kind='local_alias_action'")[0] + ")\n)"


def _execute(conn, statements):
    # executescript implicitly commits, so never use it in a migration.
    for sql in statements:
        conn.execute(sql)


def _shape(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    tables = {name: [tuple(r) for r in conn.execute(f'PRAGMA table_info("{name}")')] for name in names}
    definitions = [
        (r[0], r[1], r[2])
        for r in conn.execute("SELECT type,name,sql FROM sqlite_master WHERE type IN ('table','index') AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name")
    ]
    return tables, definitions


def _v1_to_v2(conn, timestamp):
    conn.execute("ALTER TABLE approvals RENAME TO approvals_legacy_v1")
    _execute(conn, [_table("schema_migrations"), _table("control_state"), _v2_approval(), _v2_effect()])
    conn.execute("CREATE UNIQUE INDEX approvals_mission_exact ON approvals(mission_id,action_id,epoch,arguments_digest)")
    conn.execute("CREATE UNIQUE INDEX effects_direct_request ON effects(request_id) WHERE owner_kind IN ('direct_ui','admin_ui')")
    conn.execute("INSERT INTO control_state(singleton,epoch,state,updated_at) VALUES (1,0,'inactive',?)", (timestamp,))
    conn.execute("INSERT INTO schema_migrations VALUES (2,?)", (timestamp,))
    conn.execute("PRAGMA user_version=2")


def _expected_shape(version):
    reference = sqlite3.connect(":memory:")
    try:
        reference.execute("PRAGMA foreign_keys=ON")
        reference.executescript(_SCHEMA)
        if version >= 2:
            _v1_to_v2(reference, 0)
        if version == 3:
            _v2_to_v3(reference, 0, None)
        return _shape(reference)
    finally:
        reference.close()


def _row_digest(conn, table, columns):
    rows = [tuple(r) for r in conn.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY id")]
    data = json.dumps(rows, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    return len(rows), hashlib.sha256(data).hexdigest()


def _v2_to_v3(conn, timestamp, failpoint):
    for sql in _statements():
        if sql.startswith("CREATE TABLE local_alias_"):
            conn.execute(sql)
    for table in ("approvals", "effects"):
        rebuilt = _table(table).replace(f"CREATE TABLE {table} (", f"CREATE TABLE {table}_v3 (", 1)
        if table == "effects":
            # The copied graph must reference itself, not the table being
            # retired. SQLite rewrites this self-reference on the final rename.
            rebuilt = rebuilt.replace("REFERENCES effects(id)", "REFERENCES effects_v3(id)")
        conn.execute(rebuilt)
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        dest_columns = columns + (["owner_kind", "local_action_id"] if table == "approvals" else [])
        selections = columns + (["'mission'", "NULL"] if table == "approvals" else [])
        conn.execute(f"INSERT INTO {table}_v3 ({','.join(dest_columns)}) SELECT {','.join(selections)} FROM {table}")
        before = _row_digest(conn, table, columns)
        after = _row_digest(conn, table + "_v3", columns)
        if before[0] != after[0] or failpoint == table + "_count_mismatch":
            _fail()
        if before[1] != after[1] or failpoint == table + "_digest_mismatch":
            _fail()
    # Defer self-referential effect FKs until both table swaps are complete.
    conn.execute("PRAGMA defer_foreign_keys=ON")
    for table in ("approvals", "effects"):
        if failpoint == f"interrupt_immediately_before_{table}_swap":
            _fail()
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}_v3 RENAME TO {table}")
    for sql in _statements():
        if sql.startswith("CREATE UNIQUE INDEX"):
            conn.execute(sql)
    conn.execute("INSERT INTO schema_migrations VALUES (3,?)", (timestamp,))
    conn.execute("PRAGMA user_version=3")


def upgrade_effect_schema(conn: sqlite3.Connection, *, migration_failpoint: str | None = None) -> None:
    """Atomic canonical v1/v2 -> v3 upgrade. Unrecognized schemas fail closed.

    The explicit failpoint seam is for isolated migration tests only; no env,
    route or production configuration reads it. It always aborts the upgrade.
    """
    failpoints = {f"{t}_{v}_mismatch" for t in ("approvals", "effects") for v in ("count", "digest")}
    failpoints |= {f"interrupt_immediately_before_{t}_swap" for t in ("approvals", "effects")}
    if conn.in_transaction or (migration_failpoint is not None and migration_failpoint not in failpoints):
        _fail()
    conn.execute("PRAGMA foreign_keys=ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        _fail()
    conn.execute("PRAGMA ignore_check_constraints=OFF")
    if conn.execute("PRAGMA ignore_check_constraints").fetchone()[0] != 0:
        _fail()
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("BEGIN IMMEDIATE")
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2, 3) or _shape(conn) != _expected_shape(max(1, version)):
            _fail()
        if version >= 2:
            if conn.execute("SELECT count(*) FROM control_state WHERE singleton=1").fetchone()[0] != 1:
                _fail()
            recorded = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            if recorded != list(range(2, version + 1)):
                _fail()
        timestamp = time.time()
        if version < 2:
            _v1_to_v2(conn, timestamp)
        if version < 3:
            _v2_to_v3(conn, timestamp, migration_failpoint)
        if conn.execute("PRAGMA foreign_key_check").fetchall() or conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            _fail()
        conn.commit()
    except BaseException as error:
        conn.rollback()
        if isinstance(error, (sqlite3.DatabaseError, ValueError, TypeError, StopIteration)):
            raise MigrationReviewRequired("MIGRATION_REVIEW_REQUIRED") from error
        raise
