"""
CLI additions for Phase 4-6: task listing, memory doctor, chat repair.

Add to main.py to enable:
    python -m main tasks          # list/query subagent tasks
    python -m main doctor-memory  # run MemoryPlugin health check
    python -m main repair-chat    # check/repair chat history
"""

from __future__ import annotations

from typing import Any


def register_cli_subcommands(main_parser: Any) -> None:
    """Register Phase 4-6 CLI subcommands on the main argument parser."""
    try:
        subs = main_parser.add_subparsers(dest="phase46_command")

        # ── tasks ──────────────────────────────────────────────
        tasks_p = subs.add_parser("tasks", help="List subagent tasks")
        tasks_p.add_argument("--status", default="", help="Filter by status")
        tasks_p.add_argument("--runtime", default="", help="Filter by runtime (subagent, skill, cron)")
        tasks_p.add_argument("--limit", type=int, default=20, help="Max results")

        # ── doctor-memory ─────────────────────────────────────
        doc_p = subs.add_parser("doctor-memory", help="Run MemoryPlugin health check")

        # ── repair-chat ───────────────────────────────────────
        repair_p = subs.add_parser("repair-chat", help="Check and repair chat history")
        repair_p.add_argument("--db-path", default="", help="Path to chat database")
        repair_p.add_argument("--fix", action="store_true", help="Apply repairs (default: check only)")
        repair_p.add_argument("--dry-run", action="store_true", help="Show what would be done without changing")
    except Exception:
        pass  # argparse may already have subparsers; skip


def handle_cli_command(args: Any) -> int:
    """Handle Phase 4-6 CLI commands. Returns exit code."""
    cmd = getattr(args, "phase46_command", None)

    if cmd == "tasks":
        return _handle_tasks(args)
    elif cmd == "doctor-memory":
        return _handle_doctor_memory()
    elif cmd == "repair-chat":
        return _handle_repair_chat(args)

    return 0


def _handle_tasks(args: Any) -> int:
    import asyncio

    async def _run():
        from core.task_registry import list_tasks, get_summary
        status = getattr(args, "status", "") or None
        runtime = getattr(args, "runtime", "") or None
        limit = getattr(args, "limit", 20) or 20

        if not status and not runtime:
            s = get_summary()
            print(f"Tasks: {s.total} total, {s.active} active, {s.failures} failures")
            return

        tasks = list_tasks(status=status, runtime=runtime, limit=limit)
        for t in tasks:
            print(f"  {t.task_id[:8]}... [{t.status.value}] {t.task_kind or t.runtime.value}")
            if t.result_summary:
                print(f"    → {t.result_summary[:120]}")

    asyncio.run(_run())
    return 0


def _handle_doctor_memory() -> int:
    import asyncio

    async def _run():
        from core.memory_plugin.slot import get_active_memory_plugin
        plugin = get_active_memory_plugin()
        if plugin is None:
            print("No MemoryPlugin active.")
            return
        health = await plugin.health()
        doctor = await plugin.doctor()
        print(f"Backend: {health.backend}")
        print(f"  OK: {health.ok}")
        print(f"  Index size: {health.index_size}")
        print(f"  Errors: {health.error_count}")
        print(f"  Doctor: {doctor}")

    asyncio.run(_run())
    return 0


def _handle_repair_chat(args: Any) -> int:
    from core.session_repair import check_chat_history, repair_chat_history

    db_path = getattr(args, "db_path", "") or ""
    if not db_path:
        from pathlib import Path
        db_path = str(Path("database") / "chat.db")

    do_fix = getattr(args, "fix", False)
    dry_run = getattr(args, "dry_run", False)

    if do_fix:
        report = repair_chat_history(db_path, dry_run=dry_run)
        print(f"Repair: {report.fixes_applied} fixes applied, {len(report.issues)} issues found")
    else:
        report = check_chat_history(db_path)
        print(f"Check: {'OK' if report.ok else 'ISSUES FOUND'}")
        print(f"  Tables: {report.tables_checked}, Rows: {report.rows_checked}")

    for issue in report.issues:
        print(f"  [{issue.severity}] {issue.table}: {issue.message}")

    return 0 if report.ok else 1
