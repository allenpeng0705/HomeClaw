"""
Memory backends: Cognee adapter, Chroma, knowledge base, etc.

Apply Instructor/litellm patch as soon as this package is imported so cognify
works with local LLMs (before any code imports cognee or instructor).
"""
from __future__ import annotations

try:
    from memory.instructor_patch import apply_instructor_patch_for_local_llm
    apply_instructor_patch_for_local_llm()
except Exception:
    pass
