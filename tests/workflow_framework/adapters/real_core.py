from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

import httpx


class RealCoreRunner:
    def __init__(self, root: Path, trace_dir: Path, api_key: str = "", base_url: str = "http://127.0.0.1:9000") -> None:
        self.root = root
        self.trace_dir = trace_dir
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.proc: Optional[subprocess.Popen] = None
        self._baseline_port_pids: Dict[int, Set[int]] = {}

    def _use_env_proxy(self) -> bool:
        """Use env proxies for remote targets, but bypass for localhost."""
        try:
            host = (urlparse(self.base_url).hostname or "").strip().lower()
        except Exception:
            host = ""
        return host not in {"127.0.0.1", "localhost", "::1"}

    def _client(self, timeout_sec: float) -> httpx.Client:
        return httpx.Client(timeout=timeout_sec, trust_env=self._use_env_proxy())

    def _auth_disabled(self) -> bool:
        try:
            with self._client(2.0) as client:
                r = client.get(f"{self.base_url}/ready")
                if r.status_code != 200:
                    return False
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                if isinstance(data, dict):
                    return bool(data.get("auth_enabled") is False)
        except Exception:
            pass
        return False

    def start(self) -> None:
        self._baseline_port_pids = {
            9000: self._pids_on_port(9000),
            5066: self._pids_on_port(5066),
        }
        env = dict(os.environ)
        env.update({"HOMECLAW_WORKFLOW_TRACE": "1", "HOMECLAW_WORKFLOW_TRACE_DIR": str(self.trace_dir)})
        self.proc = subprocess.Popen(
            ["python3", "-m", "main", "start", "--no-open-browser"],
            cwd=str(self.root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # Keep core and its spawned workers in one process group for clean teardown.
            start_new_session=True,
        )

    def _pids_on_port(self, port: int) -> Set[int]:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{int(port)}"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            return set()
        pids: Set[int] = set()
        for line in out.splitlines():
            s = (line or "").strip()
            if not s:
                continue
            try:
                pids.add(int(s))
            except Exception:
                continue
        return pids

    def _kill_pid(self, pid: int, sig: int) -> None:
        try:
            os.kill(int(pid), sig)
        except Exception:
            pass

    def _kill_process_group(self) -> None:
        if self.proc is None:
            return
        try:
            pgid = os.getpgid(self.proc.pid)
        except Exception:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            return
        # Give children a moment to shutdown gracefully.
        t0 = time.time()
        while time.time() - t0 < 4.0:
            if self.proc.poll() is not None:
                break
            time.sleep(0.2)
        if self.proc.poll() is None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                pass

    def _cleanup_residual_ports(self) -> None:
        # Only kill processes that appeared after runner start on target ports.
        for port in (9000, 5066):
            before = self._baseline_port_pids.get(port, set())
            now = self._pids_on_port(port)
            for pid in sorted(now - before):
                self._kill_pid(pid, signal.SIGTERM)
        time.sleep(0.5)
        for port in (9000, 5066):
            before = self._baseline_port_pids.get(port, set())
            now = self._pids_on_port(port)
            for pid in sorted(now - before):
                self._kill_pid(pid, signal.SIGKILL)

    def wait_ready(self, timeout_sec: int = 60) -> bool:
        t0 = time.time()
        while (time.time() - t0) < timeout_sec:
            try:
                with self._client(2.0) as client:
                    r = client.get(f"{self.base_url}/ready")
                    if r.status_code == 200:
                        return True
            except Exception:
                pass
            time.sleep(1.0)
        return False

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def run_prompt(self, prompt: str, user_id: str = "workflow-test-user", timeout_sec: int = 600) -> Dict[str, Any]:
        body = {
            "user_id": user_id,
            "text": prompt,
            "channel_name": "workflow-test",
            "async": True,
        }
        with self._client(30.0) as client:
            r = client.post(f"{self.base_url}/inbound", json=body, headers=self._headers())
            if r.status_code == 401 and not self.api_key and self._auth_disabled():
                r = client.post(f"{self.base_url}/inbound", json=body)
            r.raise_for_status()
            payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        request_id = str((payload or {}).get("request_id") or "").strip()
        if not request_id:
            raise RuntimeError(f"inbound did not return request_id: {payload}")
        t0 = time.time()
        last_hint: Optional[str] = None
        while (time.time() - t0) < timeout_sec:
            with self._client(20.0) as client:
                rr = client.get(
                    f"{self.base_url}/inbound/result",
                    params={"request_id": request_id},
                    headers=self._headers(),
                )
                if rr.status_code == 401 and not self.api_key and self._auth_disabled():
                    rr = client.get(
                        f"{self.base_url}/inbound/result",
                        params={"request_id": request_id},
                    )
            if rr.status_code == 202:
                try:
                    p = rr.json() if rr.headers.get("content-type", "").startswith("application/json") else {}
                    if isinstance(p, dict) and (p.get("text_preview") or "").strip():
                        last_hint = "pending_with_preview"
                except Exception:
                    pass
                time.sleep(0.5)
                continue
            rr.raise_for_status()
            data = rr.json() if rr.headers.get("content-type", "").startswith("application/json") else {}
            status = str((data or {}).get("status") or "").strip().lower()
            if status in ("done", "cancelled"):
                return data
            last_hint = f"unexpected_status={status!r}"
            time.sleep(0.5)
        raise TimeoutError(
            f"async inbound timed out after {timeout_sec}s for request_id={request_id} "
            f"(still pending or never reached done/cancelled). last_hint={last_hint!r}. "
            f"Increase timeout via --inbound-timeout or HOMECLAW_WORKFLOW_INBOUND_TIMEOUT_SEC."
        )

    def stop(self) -> None:
        try:
            self._kill_process_group()
        finally:
            self._cleanup_residual_ports()
            self.proc = None

