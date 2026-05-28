"""Tests for workspace MEMORY.md — Phase 2: OpenClaw-inspired workspace memory files."""

from __future__ import annotations

from pathlib import Path

from base.workspace import (
    CANONICAL_WORKSPACE_MEMORY_FILENAME,
    LEGACY_WORKSPACE_MEMORY_FILENAME,
    resolve_workspace_memory_path,
    load_workspace_memory_file,
    load_memory_corpus_files,
)


class TestWorkspaceMemoryFile:
    """MEMORY.md resolution and loading."""

    def test_constants(self):
        assert CANONICAL_WORKSPACE_MEMORY_FILENAME == "MEMORY.md"
        assert LEGACY_WORKSPACE_MEMORY_FILENAME == "memory.md"

    def test_resolve_nonexistent_directory(self, tmp_path):
        nonexistent = tmp_path / "nonexistent"
        assert resolve_workspace_memory_path(workspace_dir=nonexistent) is None

    def test_resolve_no_file(self, tmp_path):
        assert resolve_workspace_memory_path(workspace_dir=tmp_path) is None

    def test_resolve_canonical(self, tmp_path):
        p = tmp_path / "MEMORY.md"
        p.write_text("# Workspace Memory")
        resolved = resolve_workspace_memory_path(workspace_dir=tmp_path)
        assert resolved == p

    def test_resolve_legacy_fallback(self, tmp_path):
        p = tmp_path / "memory.md"
        p.write_text("# Legacy Memory")
        resolved = resolve_workspace_memory_path(workspace_dir=tmp_path)
        assert resolved == p

    def test_resolve_canonical_preferred(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text("canonical")
        (tmp_path / "memory.md").write_text("legacy")
        resolved = resolve_workspace_memory_path(workspace_dir=tmp_path)
        assert resolved is not None
        assert resolved.name == "MEMORY.md"

    def test_load_workspace_memory(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text("# Project Memory\n\nKey decisions here.")
        content = load_workspace_memory_file(workspace_dir=tmp_path)
        assert content is not None
        assert "Project Memory" in content
        assert "Key decisions" in content

    def test_load_workspace_memory_nonexistent(self, tmp_path):
        assert load_workspace_memory_file(workspace_dir=tmp_path) is None

    def test_load_workspace_memory_truncation(self, tmp_path):
        long_content = "x" * 5000
        (tmp_path / "MEMORY.md").write_text(long_content)
        content = load_workspace_memory_file(workspace_dir=tmp_path, max_chars=100)
        assert content is not None
        assert len(content) <= 200  # 100 chars + truncation note
        assert "Truncated" in content

    def test_load_memory_corpus_files(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "preferences.md").write_text("User prefers dark mode.")
        (memory_dir / "projects.md").write_text("Active: HomeClaw v2.")
        (tmp_path / "other.md").write_text("Not in corpus.")  # not under memory/

        corpus = load_memory_corpus_files(workspace_dir=tmp_path)
        paths = {f["path"] for f in corpus}
        assert "memory/preferences.md" in paths
        assert "memory/projects.md" in paths
        assert "other.md" not in paths  # only memory/**/*.md

    def test_load_memory_corpus_empty(self, tmp_path):
        corpus = load_memory_corpus_files(workspace_dir=tmp_path)
        assert corpus == []

    def test_load_memory_corpus_max_files(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        for i in range(30):
            (memory_dir / f"doc_{i:02d}.md").write_text(f"content {i}")

        corpus = load_memory_corpus_files(workspace_dir=tmp_path, max_files=5)
        assert len(corpus) == 5

    def test_load_memory_corpus_max_chars(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "big.md").write_text("A" * 5000)

        corpus = load_memory_corpus_files(workspace_dir=tmp_path, max_chars_per_file=100)
        assert len(corpus) == 1
        assert len(corpus[0]["content"]) <= 100
