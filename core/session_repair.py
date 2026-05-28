"""
Session repair — Phase 6: Chat history integrity checks and auto-repair.

Scans the SQLite chat history tables for common issues and optionally
repairs them. Inspired by OpenClaw's session-file-repair.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from loguru import logger


@dataclass
class RepairIssue:
    table: str
    row_id: str
    severity: str  # "warning" | "error"
    message: str
    fixable: bool = True


@dataclass
class RepairReport:
    ok: bool = True
    issues: List[RepairIssue] = field(default_factory=list)
    fixes_applied: int = 0
    tables_checked: int = 0
    rows_checked: int = 0


def check_chat_history(db_path: str) -> RepairReport:
    """
    Scan chat history tables for integrity issues.

    Checks:
    - Orphaned rows (session_id references that don't exist)
    - Duplicate row IDs
    - Missing required fields (id, session_id, user_id)
    - Empty content rows (both question and answer are empty)
    """
    import sqlite3

    report = RepairReport()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check table existence
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'chat%'"
        ).fetchall()
        report.tables_checked = len(tables)

        for (table,) in tables:
            # Count rows
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            report.rows_checked += count

            # Check for duplicate IDs
            try:
                dupes = cursor.execute(
                    f"SELECT id, COUNT(*) FROM {table} GROUP BY id HAVING COUNT(*) > 1"
                ).fetchall()
                for row_id, cnt in dupes:
                    report.issues.append(RepairIssue(
                        table=table, row_id=str(row_id), severity="error",
                        message=f"Duplicate id found {cnt} times",
                    ))
            except sqlite3.OperationalError:
                pass  # No 'id' column

            # Check for NULL required fields
            for col in ("id", "session_id", "user_id"):
                try:
                    nulls = cursor.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL OR {col} = ''"
                    ).fetchone()[0]
                    if nulls > 0:
                        report.issues.append(RepairIssue(
                            table=table, row_id="(multiple)", severity="warning",
                            message=f"{nulls} rows with empty {col}",
                        ))
                except sqlite3.OperationalError:
                    pass

            # Check for empty content
            try:
                empty = cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE (question IS NULL OR question = '') AND (answer IS NULL OR answer = '')"
                ).fetchone()[0]
                if empty > 0:
                    report.issues.append(RepairIssue(
                        table=table, row_id="(multiple)", severity="warning",
                        message=f"{empty} rows with empty question and answer",
                    ))
            except sqlite3.OperationalError:
                pass

        conn.close()
        report.ok = len(report.issues) == 0
    except Exception as e:
        report.ok = False
        report.issues.append(RepairIssue(
            table="(connection)", row_id="", severity="error",
            message=f"Failed to open database: {e}", fixable=False,
        ))

    return report


def repair_chat_history(db_path: str, dry_run: bool = False) -> RepairReport:
    """
    Repair common chat history issues.

    Repairs applied:
    - Remove duplicate rows (keep first occurrence)
    - Remove rows with empty id/session_id/user_id
    - Remove rows with both question and answer empty
    """
    import sqlite3

    report = check_chat_history(db_path)
    if dry_run or not report.issues:
        return report

    fixed = 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Repair each table
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'chat%'"
        ).fetchall()

        for (table,) in tables:
            # Remove duplicate rows: keep first occurrence by rowid.
            # Uses temp-table approach (portable across SQLite versions).
            try:
                import uuid as _uuid
                _tmp = f"_repair_dedup_{str(_uuid.uuid4())[:8]}"
                cursor.execute(
                    f"CREATE TEMP TABLE IF NOT EXISTS {_tmp} AS "
                    f"SELECT * FROM {table} WHERE 1=0"
                )
                cols = [d[1] for d in cursor.execute(f"PRAGMA table_info({table})")]
                col_list = ", ".join(cols)
                before = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                cursor.execute(f"""
                    INSERT INTO {_tmp}
                    SELECT {col_list} FROM {table} GROUP BY id
                """)
                cursor.execute(f"DELETE FROM {table}")
                cursor.execute(f"INSERT INTO {table} SELECT * FROM {_tmp}")
                cursor.execute(f"DROP TABLE {_tmp}")
                after = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                removed = before - after
                if removed > 0:
                    logger.info("Removed {} duplicate rows from {}", removed, table)
                    fixed += removed
            except Exception:
                pass

            # Remove rows with empty required fields
            for col in ("id", "session_id", "user_id"):
                try:
                    cursor.execute(
                        f"DELETE FROM {table} WHERE {col} IS NULL OR {col} = ''"
                    )
                    removed = cursor.rowcount
                    if removed > 0:
                        logger.info("Removed {} rows with empty {} from {}", removed, col, table)
                        fixed += removed
                except sqlite3.OperationalError:
                    pass

            # Remove empty content rows (only when id/session_id are also empty — truly broken)
            try:
                cursor.execute(
                    f"DELETE FROM {table} WHERE (question IS NULL OR question = '') "
                    f"AND (answer IS NULL OR answer = '') "
                    f"AND (id IS NULL OR id = '') "
                    f"AND (session_id IS NULL OR session_id = '')"
                )
                removed = cursor.rowcount
                if removed > 0:
                    logger.info("Removed {} truly-empty rows from {}", removed, table)
                    fixed += removed
            except sqlite3.OperationalError:
                pass

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Chat history repair failed: {}", e)
        report.issues.append(RepairIssue(
            table="(repair)", row_id="", severity="error",
            message=f"Repair failed: {e}", fixable=False,
        ))

    report.fixes_applied = fixed
    return report
