"""
Standard first-level folders under each user's sandbox: ``homeclaw_root/{user_id}/<name>/``.

- Used by ``folder_list`` / ``file_find`` to auto-create a folder on first access when missing
  (not under global ``share/`` — see ``tools.builtin._try_create_standard_sandbox_subdir``).
- Used by planner DAG folder extraction and LLM prompts so names stay in sync.

``share`` in :data:`FOLDER_NAMES_FOR_USER_MESSAGE` means the **global** shared folder
(``homeclaw_root/share``), same as tool path ``share``. It is **not** in
:data:`STANDARD_USER_SANDBOX_SUBDIRS` so we do not auto-create under the global share root
via the per-user mkdir path.

See: docs_design/FileSandboxDesign.md, docs_design/FolderSemanticsAndInference.md
"""

from __future__ import annotations

import re
from typing import FrozenSet, Tuple

# Per-user only; mkdir when user lists this path and it is missing (under their sandbox).
STANDARD_USER_SANDBOX_SUBDIRS: FrozenSet[str] = frozenset(
    {
        "documents",
        "downloads",
        "images",
        "output",
        "work",
        "knowledge",
        "videos",
        "audios",
    }
)

# For regex / substring extraction from user text (includes global share keyword).
# Order: longer names before shorter where it matters; "share" last.
FOLDER_NAMES_FOR_USER_MESSAGE: Tuple[str, ...] = (
    "documents",
    "downloads",
    "knowledge",
    "images",
    "output",
    "videos",
    "audios",
    "work",
    "share",
)


def folder_names_pattern_for_regex() -> str:
    """Alternation for re: longest names first to avoid partial matches where relevant."""
    names = sorted(FOLDER_NAMES_FOR_USER_MESSAGE, key=len, reverse=True)
    return "|".join(re.escape(n) for n in names)
