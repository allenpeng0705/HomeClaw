"""
Interactive process sessions (PTY/ConPTY) for HomeClaw.

This module provides a small manager that lets Core (and tools) start long‑lived
processes with stdin/stdout interaction, instead of one‑shot subprocess calls.
Sessions are keyed by session_id and owned by a user_id (and optional friend_id).
"""

from __future__ import annotations

import asyncio
import os
import platform
import pty
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


IS_WINDOWS = platform.system() == "Windows"


@dataclass
class InteractiveChunk:
    seq: int
    text: str
    timestamp: float


@dataclass
class InteractiveSession:
    session_id: str
    user_id: str
    friend_id: Optional[str]
    command: str
    cwd: Optional[str]
    created_at: float
    last_activity_at: float
    status: str = "running"  # running | exited | error | killed
    exit_code: Optional[int] = None
    _buffer: List[InteractiveChunk] = field(default_factory=list)
    _next_seq: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)
    max_buffer_chars: int = 200_000  # cap total buffer size; configurable via tools.interactive_max_buffer_bytes

    def append_output(self, text: str) -> None:
        now = time.time()
        with self._lock:
            self.last_activity_at = now
            if not text:
                return
            # Split into reasonably sized chunks so UI can stream.
            max_chunk = 4000
            for i in range(0, len(text), max_chunk):
                chunk = text[i : i + max_chunk]
                self._buffer.append(InteractiveChunk(seq=self._next_seq, text=chunk, timestamp=now))
                self._next_seq += 1
            # Keep only the last N chars across chunks (configurable cap).
            max_chars = max(1000, self.max_buffer_chars)
            total = 0
            pruned: List[InteractiveChunk] = []
            for c in reversed(self._buffer):
                total += len(c.text)
                pruned.append(c)
                if total >= max_chars:
                    break
            self._buffer = list(reversed(pruned))

    def read_from(self, from_seq: int = 1) -> Tuple[List[InteractiveChunk], int]:
        """Return chunks with seq >= from_seq and latest seq value."""
        with self._lock:
            chunks = [c for c in self._buffer if c.seq >= from_seq]
            last_seq = self._next_seq - 1
        return chunks, last_seq


def _safe_int(val: Any, default: int) -> int:
    """Parse int from config; return default on None, invalid type, or ValueError. Never raises."""
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def get_interactive_config() -> dict:
    """Read interactive session limits from config (tools.interactive_*). Returns dict with defaults when keys missing. Never raises."""
    try:
        from base.util import Util
        meta = getattr(Util(), "get_core_metadata", lambda: None) and Util().get_core_metadata()
        tools = getattr(meta, "tools_config", None) or {}
    except Exception:
        tools = {}
    if not isinstance(tools, dict):
        tools = {}
    return {
        "max_sessions_per_user": max(1, _safe_int(tools.get("interactive_max_sessions_per_user"), 3)),
        "idle_ttl_sec": max(60, _safe_int(tools.get("interactive_idle_ttl_sec"), 1800)),
        "max_buffer_chars": max(1000, _safe_int(tools.get("interactive_max_buffer_bytes"), 200_000)),
    }


class InteractiveSessionManager:
    """Owns interactive sessions. Unix: PTY; Windows: ConPTY via pywinpty when available."""

    def __init__(
        self,
        max_sessions_per_user: int = 3,
        idle_ttl_sec: int = 1800,
        max_buffer_chars: int = 200_000,
    ):
        self._sessions: Dict[str, InteractiveSession] = {}
        # Unix-only: track PTY master fds so we can write stdin. Keyed by session_id.
        self._unix_master_fds: Dict[str, int] = {}
        # Windows-only: track pywinpty PtyProcess objects per session when available.
        self._win_procs: Dict[str, "object"] = {}
        self._by_user: Dict[str, List[str]] = {}
        self._max_sessions_per_user = max(1, int(max_sessions_per_user or 1))
        self._idle_ttl_sec = max(60, int(idle_ttl_sec or 1800))
        self._max_buffer_chars = max(1000, int(max_buffer_chars or 200_000))
        self._lock = asyncio.Lock()

    async def start_session(
        self,
        user_id: str,
        friend_id: Optional[str],
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str]:
        """Start a new interactive session. Returns (session_id, initial_output)."""
        if not (command or "").strip():
            raise ValueError("command is empty")
        uid = (user_id or "").strip() or "unknown"
        now = time.time()
        async with self._lock:
            current = self._by_user.get(uid) or []
            # GC idle sessions for this user.
            current = [sid for sid in current if self._sessions.get(sid)]
            self._by_user[uid] = current
            if len(current) >= self._max_sessions_per_user:
                raise RuntimeError("Too many interactive sessions for this user")
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            sess = InteractiveSession(
                session_id=session_id,
                user_id=uid,
                friend_id=(friend_id or "").strip() or None,
                command=command,
                cwd=(cwd or "").strip() or None,
                created_at=now,
                last_activity_at=now,
                max_buffer_chars=self._max_buffer_chars,
            )
            self._sessions[session_id] = sess
            current.append(session_id)
            self._by_user[uid] = current
        # Spawn process outside the lock.
        if IS_WINDOWS:
            try:
                await self._start_win_conpty(sess, env or {})
                return session_id, "".join(c.text for c in sess.read_from(1)[0])
            except Exception:
                # Fallback: clear, actionable message when ConPTY/pywinpty not available.
                sess.append_output(
                    "Interactive sessions on Windows require the optional 'pywinpty' dependency and a supported console. "
                    "For now, use a Unix-like environment (macOS, Linux, or WSL) to run interactive shells, "
                    "or install pywinpty and restart Core.\n"
                )
                sess.status = "error"
                sess.exit_code = 1
                return session_id, "".join(c.text for c in sess.read_from(1)[0])
        else:
            await self._start_unix_pty(sess, env or {})
            return session_id, "".join(c.text for c in sess.read_from(1)[0])

    async def _start_win_conpty(self, sess: InteractiveSession, env: Dict[str, str]) -> None:
        """Spawn command under a ConPTY on Windows using pywinpty (optional dependency)."""
        # Import locally so Unix installs don't need pywinpty.
        try:
            from pywinpty import PtyProcess  # type: ignore
        except ImportError as e:  # pragma: no cover - Windows-only
            raise RuntimeError("pywinpty not installed") from e

        loop = asyncio.get_running_loop()
        cmd = sess.command
        cwd = sess.cwd or os.getcwd()

        def _run():
            try:
                proc = PtyProcess.spawn(cmd, cwd=cwd, env={**os.environ, **env})
            except Exception as e:  # pragma: no cover - Windows-only
                loop.call_soon_threadsafe(sess.append_output, f"Failed to start interactive session: {e!s}\n")
                sess.status = "error"
                sess.exit_code = 1
                return
            # Remember proc so write()/stop() can use it.
            try:
                loop.call_soon_threadsafe(self._win_procs.__setitem__, sess.session_id, proc)
            except Exception:
                pass
            try:
                while True:
                    try:
                        data = proc.read(4096)
                    except Exception:
                        break
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
                    loop.call_soon_threadsafe(sess.append_output, text)
            finally:
                try:
                    proc.close()
                except Exception:
                    pass
                try:
                    loop.call_soon_threadsafe(self._win_procs.pop, sess.session_id, None)
                except Exception:
                    pass
                sess.status = "exited"
                sess.exit_code = 0

        threading.Thread(target=_run, daemon=True).start()

    async def _start_unix_pty(self, sess: InteractiveSession, env: Dict[str, str]) -> None:
        """Spawn command under a PTY on Unix-like systems."""
        loop = asyncio.get_running_loop()
        cmd = sess.command
        cwd = sess.cwd or os.getcwd()
        # Use a thread to run blocking PTY logic; feed output back via callbacks.
        def _run():
            try:
                argv = ["/bin/sh", "-lc", cmd]
                pid, master_fd = pty.fork()
                if pid == 0:
                    # Child.
                    try:
                        os.chdir(cwd)
                    except Exception:
                        pass
                    os.execvpe(argv[0], argv, {**os.environ, **env})
                else:
                    # Parent: remember master_fd so write() can send stdin.
                    try:
                        loop.call_soon_threadsafe(self._unix_master_fds.__setitem__, sess.session_id, master_fd)
                    except Exception:
                        pass
                    try:
                        while True:
                            try:
                                data = os.read(master_fd, 4096)
                            except OSError:
                                break
                            if not data:
                                break
                            text = data.decode("utf-8", errors="replace")
                            loop.call_soon_threadsafe(sess.append_output, text)
                    finally:
                        try:
                            os.close(master_fd)
                        except OSError:
                            pass
                        # Remove fd from manager map.
                        try:
                            loop.call_soon_threadsafe(self._unix_master_fds.pop, sess.session_id, None)
                        except Exception:
                            pass
                        # Best-effort: we don't have exit code from PTY easily; mark exited.
                        sess.status = "exited"
                        sess.exit_code = 0
            except Exception:
                sess.append_output("Error: failed to start PTY session.\n")
                sess.status = "error"
                sess.exit_code = 1
        threading.Thread(target=_run, daemon=True).start()

    async def write(self, session_id: str, data: str) -> None:
        """Write stdin to an interactive session (Unix PTY only for now)."""
        if not data:
            return
        if IS_WINDOWS:
            # Windows: write via pywinpty PtyProcess when available.
            proc = self._win_procs.get(session_id)
            if proc is None:
                return
            try:
                # PtyProcess.write expects str; it will handle encoding.
                proc.write(data)
            except Exception:
                return
        else:
            # Unix: snapshot fd without holding lock too long.
            master_fd = self._unix_master_fds.get(session_id)
            if master_fd is None:
                return
            try:
                os.write(master_fd, data.encode("utf-8"))
            except OSError:
                # PTY likely closed; ignore.
                return

    async def read(self, session_id: str, from_seq: int = 1) -> Tuple[List[InteractiveChunk], str, Optional[int], str]:
        """Return (chunks, status, exit_code, command)."""
        async with self._lock:
            sess = self._sessions.get(session_id)
        if not sess:
            raise KeyError("Unknown session_id")
        chunks, _ = sess.read_from(from_seq)
        return chunks, sess.status, sess.exit_code, sess.command

    async def stop(self, session_id: str) -> None:
        """Mark session as killed and best-effort terminate underlying process."""
        async with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return
            sess.status = "killed"
            sess.exit_code = None
        # Best-effort: close PTY / terminate process.
        if IS_WINDOWS:
            proc = self._win_procs.pop(session_id, None)
            if proc is not None:
                try:
                    proc.close()
                except Exception:
                    pass
        else:
            fd = self._unix_master_fds.pop(session_id, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

