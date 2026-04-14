#!/usr/bin/env python3
"""
Optional HTTP smoke / evaluation for M-flow (sidecar). Does not import HomeClaw memory or Core.

Requires M-flow API running (e.g. http://127.0.0.1:8000). See docs/m-flow-http-evaluation.md.

Usage:
  export MFLOW_BASE_URL=http://127.0.0.1:8000
  python scripts/eval_m_flow_http.py --smoke
  python scripts/eval_m_flow_http.py --full

Env:
  MFLOW_BASE_URL   (default http://127.0.0.1:8000)
  MFLOW_DATASET    (default hc_eval_<date> for --full; --smoke uses hc_eval_smoke)
  MFLOW_BEARER     optional Bearer token for Authorization header
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx", file=sys.stderr)
    sys.exit(1)


# Tiny default corpus + questions (Phase B lite). Replace with --corpus-file for custom text.
DEFAULT_CORPUS = """
Episode 1 — Project Chimera (2026-04-01)
The team picked SQLite for the edge cache and set a P99 latency target under 500ms.
Lead engineer: Dana Ortiz. Rollback plan: feature flag chimera.cache.enabled.

Episode 2 — Incident 42
On 2026-04-02, cache eviction caused a spike; Dana disabled the flag and restored P99 to 420ms.
"""

DEFAULT_QUESTIONS: list[tuple[str, str]] = [
    ("What P99 target was set for Chimera?", "EPISODIC"),
    ("Who was the lead engineer on Chimera?", "EPISODIC"),
    ("What was P99 after disabling the flag in Incident 42?", "CHUNKS_LEXICAL"),
]


def _base_url() -> str:
    return (os.environ.get("MFLOW_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def _headers(bearer: str | None) -> dict[str, str]:
    h: dict[str, str] = {}
    if bearer:
        h["Authorization"] = f"Bearer {bearer}"
    return h


def health(client: httpx.Client, base: str, hdrs: dict[str, str]) -> None:
    r = client.get(f"{base}/health", headers=hdrs, timeout=30.0)
    r.raise_for_status()


def add_text(
    client: httpx.Client,
    base: str,
    hdrs: dict[str, str],
    text: str,
    dataset_name: str,
) -> dict[str, Any]:
    url = f"{base}/api/v1/add"
    files = {"data": ("data.txt", text.strip(), "text/plain")}
    data = {"datasetName": dataset_name}
    r = client.post(url, files=files, data=data, headers=hdrs, timeout=120.0)
    r.raise_for_status()
    return r.json()


def memorize(
    client: httpx.Client,
    base: str,
    hdrs: dict[str, str],
    datasets: list[str],
    memorize_timeout: float,
) -> dict[str, Any]:
    url = f"{base}/api/v1/memorize"
    body = {
        "datasets": datasets,
        "run_in_background": False,
    }
    r = client.post(url, json=body, headers={**hdrs, "Content-Type": "application/json"}, timeout=memorize_timeout)
    r.raise_for_status()
    return r.json()


def search(
    client: httpx.Client,
    base: str,
    hdrs: dict[str, str],
    query: str,
    recall_mode: str,
    datasets: list[str],
    top_k: int,
    search_timeout: float,
) -> Any:
    url = f"{base}/api/v1/search"
    body: dict[str, Any] = {
        "query": query,
        "recall_mode": recall_mode.upper(),
        "top_k": top_k,
        "datasets": datasets,
    }
    r = client.post(url, json=body, headers={**hdrs, "Content-Type": "application/json"}, timeout=search_timeout)
    r.raise_for_status()
    return r.json()


def _truncate(s: Any, max_len: int = 600) -> str:
    t = json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def run_smoke(
    base: str,
    bearer: str | None,
    dataset: str,
    memorize_timeout: float,
    search_timeout: float,
    top_k: int,
) -> int:
    hdrs = _headers(bearer)
    text = "Smoke fact: the evaluation token is SMOKE-7f3a. Remember this exact string."
    with httpx.Client() as client:
        t0 = time.perf_counter()
        health(client, base, hdrs)
        print(f"health OK ({(time.perf_counter() - t0) * 1000:.0f} ms)")

        t0 = time.perf_counter()
        add_text(client, base, hdrs, text, dataset)
        print(f"add OK ({(time.perf_counter() - t0) * 1000:.0f} ms)")

        t0 = time.perf_counter()
        mem = memorize(client, base, hdrs, [dataset], memorize_timeout)
        print(f"memorize OK ({(time.perf_counter() - t0) * 1000:.0f} ms) {_truncate(mem, 200)}")

        for mode in ("EPISODIC", "CHUNKS_LEXICAL"):
            t0 = time.perf_counter()
            res = search(
                client,
                base,
                hdrs,
                "What is the evaluation token?",
                mode,
                [dataset],
                top_k,
                search_timeout,
            )
            snippet = _truncate(res, 800)
            print(f"search {mode} OK ({(time.perf_counter() - t0) * 1000:.0f} ms)\n{snippet}\n")

    return 0


def run_full(
    base: str,
    bearer: str | None,
    dataset: str,
    corpus: str,
    questions: list[tuple[str, str]],
    memorize_timeout: float,
    search_timeout: float,
    top_k: int,
) -> int:
    hdrs = _headers(bearer)
    with httpx.Client() as client:
        health(client, base, hdrs)
        print("health OK")

        t0 = time.perf_counter()
        add_text(client, base, hdrs, corpus, dataset)
        print(f"add OK ({(time.perf_counter() - t0) * 1000:.0f} ms)")

        t0 = time.perf_counter()
        mem = memorize(client, base, hdrs, [dataset], memorize_timeout)
        print(f"memorize OK ({(time.perf_counter() - t0) * 1000:.0f} ms) {_truncate(mem, 300)}")

        for q, mode in questions:
            t0 = time.perf_counter()
            try:
                res = search(client, base, hdrs, q, mode, [dataset], top_k, search_timeout)
                ms = (time.perf_counter() - t0) * 1000
                print(f"\nQ ({mode}, {ms:.0f} ms): {q}")
                print(_truncate(res, 1200))
            except Exception as e:
                print(f"\nQ FAIL ({mode}): {q}\n  {e}", file=sys.stderr)
                return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="M-flow HTTP evaluation (optional; does not touch HomeClaw memory)")
    p.add_argument("--base-url", default=None, help="M-flow API base (default env MFLOW_BASE_URL or http://127.0.0.1:8000)")
    p.add_argument("--dataset", default=None, help="datasetName (default env MFLOW_DATASET or hc_eval_YYYYMMDD_utc)")
    p.add_argument("--bearer", default=None, help="Bearer token (default env MFLOW_BEARER)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true", help="Phase A: tiny text + two search modes")
    g.add_argument("--full", action="store_true", help="Phase B lite: default corpus + default questions")
    p.add_argument("--corpus-file", default=None, help="Path to UTF-8 text file to ingest instead of embedded corpus (--full only)")
    p.add_argument("--memorize-timeout", type=float, default=300.0, help="Seconds (default 300)")
    p.add_argument("--search-timeout", type=float, default=120.0, help="Seconds (default 120)")
    p.add_argument("--top-k", type=int, default=5, help="search top_k (default 5)")
    args = p.parse_args()

    base = (args.base_url or _base_url()).rstrip("/")
    bearer = args.bearer if args.bearer is not None else os.environ.get("MFLOW_BEARER")
    bearer = bearer.strip() if bearer else None

    if args.smoke:
        dataset = (args.dataset or os.environ.get("MFLOW_DATASET") or "hc_eval_smoke").strip()
    else:
        default_ds = f"hc_eval_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        dataset = (args.dataset or os.environ.get("MFLOW_DATASET") or default_ds).strip()

    try:
        if args.smoke:
            return run_smoke(
                base,
                bearer,
                dataset,
                args.memorize_timeout,
                args.search_timeout,
                args.top_k,
            )
        corpus = DEFAULT_CORPUS.strip()
        if args.corpus_file:
            with open(args.corpus_file, encoding="utf-8") as f:
                corpus = f.read()
        if not corpus.strip():
            print("Corpus is empty.", file=sys.stderr)
            return 1
        return run_full(
            base,
            bearer,
            dataset,
            corpus,
            DEFAULT_QUESTIONS,
            args.memorize_timeout,
            args.search_timeout,
            args.top_k,
        )
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.response.text[:2000]}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
