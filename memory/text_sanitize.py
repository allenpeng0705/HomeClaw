"""Lightweight string sanitization for memory / embedding (no heavy imports)."""

from __future__ import annotations

import re


def strip_vmprint_file_link_block(text: str) -> str:
    """
    Remove VMPrint magazine preview boilerplate (artifact line, CRITICAL, /files/out URL) through '---'.
    Keeps user-facing answer text (e.g. formatted search results) for embeddings.
    """
    s = text or ""
    if not s.strip():
        return s
    low = s.lower()
    key = "**magazine layout (vmprint"
    i = low.find(key)
    if i < 0:
        return s
    rest = s[i:]
    m = re.search(r"\n---\s*\n", rest)
    if m:
        end = i + m.end()
        prefix = s[:i].rstrip()
        suffix = s[end:].lstrip()
        out = f"{prefix}\n\n{suffix}".strip() if suffix else prefix.strip()
        return out or s
    m2 = re.search(r"(?is)\nhttps?://\S+\s*\n+", rest)
    if m2:
        tail = rest[m2.end() :].lstrip()
        prefix = s[:i].rstrip()
        out = f"{prefix}\n\n{tail}".strip() if tail else prefix.strip()
        return out or s
    return s
