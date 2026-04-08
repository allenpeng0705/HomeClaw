"""Unit tests for memory text normalization before embedding."""

from memory.text_sanitize import strip_vmprint_file_link_block


def test_strip_vmprint_block_removes_magazine_section_through_dash_rule():
    raw = """[Local · heuristic] **Magazine layout (VMPrint / AST):** open this preview.

VMPrint daily-brief AST artifact saved: output/x.preview.html

CRITICAL: Use ONLY the URL on the next line.
https://example.com/files/out?scope=u&path=output/x.preview.html&dev_unsigned=1

---

## 搜索结果

- **标题**
  https://news.example/a
"""
    out = strip_vmprint_file_link_block(raw)
    assert "Magazine layout" not in out
    assert "files/out" not in out
    assert "搜索结果" in out
    assert "标题" in out


def test_strip_vmprint_noop_when_absent():
    s = "User asked about weather.\n\nAssistant: It will rain."
    assert strip_vmprint_file_link_block(s) == s
