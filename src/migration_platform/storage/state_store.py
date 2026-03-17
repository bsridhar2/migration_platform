"""DuckDB-backed state store — replaces PostgreSQL, zero server required."""
from __future__ import annotations
import json
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator
import duckdb
from migration_platform.core.logging import get_logger

logger = get_logger(__name__)


class StateStore:
    """
    Persistent state store using DuckDB.
    Path ":memory:" = pure in-memory (no disk writes).
    Path "file.duckdb" = persisted single file, survives restarts.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = duckdb.connect(self._db_path)
        # LangGraph runs parallel Send-fan-out nodes in a thread-pool executor.
        # All those threads share this single duckdb connection, which is NOT
        # thread-safe by itself.  A re-entrant lock serialises every execute()
        # call so concurrent codegen workers don't corrupt the connection.
        self._lock = threading.RLock()
        self._init_schema()
        logger.info("StateStore initialised", path=self._db_path)

    def _init_schema(self) -> None:
        self._exec("""
            CREATE TABLE IF NOT EXISTS migrations (
                migration_id     TEXT PRIMARY KEY,
                repo_url         TEXT NOT NULL,
                status           TEXT DEFAULT 'pending',
                approval_status  TEXT DEFAULT 'pending',
                approval_comment TEXT DEFAULT '',
                current_phase    TEXT DEFAULT 'init',
                created_at       TIMESTAMP DEFAULT current_timestamp,
                updated_at       TIMESTAMP DEFAULT current_timestamp,
                error_message    TEXT,
                state_json       JSON
            );

            CREATE TABLE IF NOT EXISTS file_index (
                migration_id TEXT NOT NULL,
                file_path    TEXT NOT NULL,
                file_type    TEXT NOT NULL,
                chunk_count  INTEGER DEFAULT 0,
                embedded     BOOLEAN DEFAULT false,
                PRIMARY KEY  (migration_id, file_path)
            );

            CREATE TABLE IF NOT EXISTS soap_integrations (
                migration_id      TEXT NOT NULL,
                service_name      TEXT NOT NULL,
                callsite_class    TEXT,
                callsite_method   TEXT,
                endpoint_url      TEXT,
                wsdl_url          TEXT,
                stub_class        TEXT,
                operations        JSON,
                migration_option  TEXT DEFAULT 'A',
                complexity        TEXT DEFAULT 'MEDIUM',
                PRIMARY KEY (migration_id, service_name, callsite_method)
            );

            CREATE TABLE IF NOT EXISTS generated_files (
                migration_id     TEXT NOT NULL,
                file_path        TEXT NOT NULL,
                file_type        TEXT NOT NULL,
                content          TEXT,
                source_chunk_ids JSON,
                build_verified   BOOLEAN DEFAULT false,
                generated_at     TIMESTAMP DEFAULT current_timestamp,
                PRIMARY KEY (migration_id, file_path)
            );

            CREATE TABLE IF NOT EXISTS progress_events (
                id              BIGINT PRIMARY KEY,
                migration_id    TEXT NOT NULL,
                event_type      TEXT,
                phase           TEXT,
                message         TEXT,
                progress_pct    DOUBLE,
                metadata        JSON,
                created_at      TIMESTAMP DEFAULT current_timestamp
            );
        """)

    # ── Thread-safe execute helper ────────────────────────────
    def _exec(self, sql: str, params: list | None = None):
        """Execute *sql* under the instance lock — safe for thread-pool callers."""
        with self._lock:
            return self._conn.execute(sql, params or [])

    # ── Migration CRUD ────────────────────────────────────────
    def create_migration(self, migration_id: str, repo_url: str) -> None:
        self._exec(
            """
            INSERT INTO migrations (migration_id, repo_url, state_json)
            VALUES (?, ?, '{}')
            ON CONFLICT (migration_id) DO NOTHING
            """,
            [migration_id, repo_url],
        )

    def update_status(self, migration_id: str, status: str, phase: str = "") -> None:
        self._exec(
            """
            UPDATE migrations
            SET status = ?, current_phase = ?, updated_at = current_timestamp
            WHERE migration_id = ?
            """,
            [status, phase, migration_id],
        )

    def set_error(self, migration_id: str, message: str) -> None:
        self._exec(
            """
            UPDATE migrations
            SET status = 'failed', error_message = ?, updated_at = current_timestamp
            WHERE migration_id = ?
            """,
            [message, migration_id],
        )

    def set_approval(
        self, migration_id: str, status: str, comment: str = ""
    ) -> None:
        self._exec(
            """
            UPDATE migrations
            SET approval_status = ?, approval_comment = ?, updated_at = current_timestamp
            WHERE migration_id = ?
            """,
            [status, comment, migration_id],
        )

    def save_state_json(self, migration_id: str, state: dict[str, Any]) -> None:
        self._exec(
            """
            UPDATE migrations SET state_json = ?, updated_at = current_timestamp
            WHERE migration_id = ?
            """,
            [json.dumps(state, default=str), migration_id],
        )

    def load_state_json(self, migration_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT state_json FROM migrations WHERE migration_id = ?",
            [migration_id],
        ).fetchone()
        return json.loads(row[0]) if row else None

    def get_migration(self, migration_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT migration_id, repo_url, status, approval_status,
                   approval_comment, current_phase, created_at, updated_at,
                   error_message, state_json
            FROM migrations WHERE migration_id = ?
            """,
            [migration_id],
        ).fetchone()
        if not row:
            return None
        keys = [
            "migration_id", "repo_url", "status", "approval_status",
            "approval_comment", "current_phase", "created_at", "updated_at",
            "error_message", "state_json",
        ]
        return dict(zip(keys, row))

    # ── File Index ────────────────────────────────────────────
    def bulk_insert_files(
        self, migration_id: str, files: list[dict[str, str]]
    ) -> None:
        rows = [
            (migration_id, f["file_path"], f["file_type"])
            for f in files
        ]
        self._conn.executemany(
            """
            INSERT INTO file_index (migration_id, file_path, file_type)
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )

    def mark_embedded(self, migration_id: str, file_path: str, chunk_count: int) -> None:
        self._exec(
            """
            UPDATE file_index
            SET embedded = true, chunk_count = ?
            WHERE migration_id = ? AND file_path = ?
            """,
            [chunk_count, migration_id, file_path],
        )

    def get_unembedded_files(self, migration_id: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT file_path FROM file_index
            WHERE migration_id = ? AND embedded = false
            ORDER BY file_type
            """,
            [migration_id],
        ).fetchall()
        return [r[0] for r in rows]

    def get_file_type_counts(self, migration_id: str) -> dict[str, int]:
        """Return the number of *embedded* files per file_type for a migration."""
        rows = self._conn.execute(
            """
            SELECT file_type,
                   SUM(CASE WHEN embedded THEN 1 ELSE 0 END) AS embedded_count
            FROM file_index
            WHERE migration_id = ?
            GROUP BY file_type
            ORDER BY file_type
            """,
            [migration_id],
        ).fetchall()
        return {row[0]: int(row[1] or 0) for row in rows}

    def get_total_file_type_counts(self, migration_id: str) -> dict[str, int]:
        """Return the *total* number of cloned files per file_type (embedded or not)."""
        rows = self._conn.execute(
            """
            SELECT file_type, COUNT(*) AS total_count
            FROM file_index
            WHERE migration_id = ?
            GROUP BY file_type
            ORDER BY file_type
            """,
            [migration_id],
        ).fetchall()
        return {row[0]: int(row[1] or 0) for row in rows}

    def get_progress(self, migration_id: str) -> dict[str, int]:
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN embedded THEN 1 ELSE 0 END) AS embedded,
                COALESCE(SUM(chunk_count), 0) AS chunks
            FROM file_index WHERE migration_id = ?
            """,
            [migration_id],
        ).fetchone()
        if not row:
            return {"total_files": 0, "embedded_files": 0, "total_chunks": 0}
        return {
            "total_files": row[0] or 0,
            "embedded_files": row[1] or 0,
            "total_chunks": row[2] or 0,
        }

    # ── SOAP Integrations ─────────────────────────────────────
    def save_soap_integration(self, migration_id: str, soap: dict[str, Any]) -> None:
        self._exec(
            """
            INSERT INTO soap_integrations
              (migration_id, service_name, callsite_class, callsite_method,
               endpoint_url, wsdl_url, stub_class, operations, migration_option, complexity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            [
                migration_id,
                soap.get("service_name", ""),
                soap.get("callsite_class", ""),
                soap.get("callsite_method", ""),
                soap.get("endpoint_url", ""),
                soap.get("wsdl_url", ""),
                soap.get("stub_class", ""),
                json.dumps(soap.get("operations", [])),
                soap.get("migration_option", "A"),
                soap.get("complexity", "MEDIUM"),
            ],
        )

    def get_soap_integrations(self, migration_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM soap_integrations WHERE migration_id = ?",
            [migration_id],
        ).fetchall()
        cols = [
            "migration_id", "service_name", "callsite_class", "callsite_method",
            "endpoint_url", "wsdl_url", "stub_class", "operations",
            "migration_option", "complexity",
        ]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["operations"] = json.loads(d["operations"]) if d["operations"] else []
            result.append(d)
        return result

    # ── Generated Files ───────────────────────────────────────
    def save_generated_file(
        self, migration_id: str, file_path: str, file_type: str,
        content: str, source_chunk_ids: list[str]
    ) -> None:
        self._exec(
            """
            INSERT INTO generated_files
              (migration_id, file_path, file_type, content, source_chunk_ids)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (migration_id, file_path) DO UPDATE SET
              content = excluded.content,
              source_chunk_ids = excluded.source_chunk_ids
            """,
            [migration_id, file_path, file_type, content, json.dumps(source_chunk_ids)],
        )

    def mark_build_verified(self, migration_id: str) -> None:
        self._exec(
            "UPDATE generated_files SET build_verified = true WHERE migration_id = ?",
            [migration_id],
        )

    def get_generated_files(self, migration_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT file_path, file_type, content, source_chunk_ids, build_verified
            FROM generated_files WHERE migration_id = ?
            """,
            [migration_id],
        ).fetchall()
        result = []
        for row in rows:
            result.append({
                "file_path": row[0],
                "file_type": row[1],
                "content": row[2],
                "source_chunk_ids": json.loads(row[3]) if row[3] else [],
                "build_verified": row[4],
            })
        return result

    # ── Progress Events ───────────────────────────────────────
    def log_progress(
        self, migration_id: str, event_type: str, phase: str,
        message: str, progress_pct: float, metadata: dict | None = None
    ) -> None:
        self._exec(
            """
            INSERT INTO progress_events
              (id, migration_id, event_type, phase, message, progress_pct, metadata)
            VALUES (
                (SELECT COALESCE(MAX(id), 0) + 1 FROM progress_events),
                ?, ?, ?, ?, ?, ?
            )
            """,
            [migration_id, event_type, phase, message, progress_pct,
             json.dumps(metadata or {})],
        )

    def close(self) -> None:
        self._conn.close()
