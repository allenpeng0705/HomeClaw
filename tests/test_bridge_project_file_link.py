"""Dev-bridge project file browser tokens and URL builder (Companion → Core GET /files/bridge-project)."""

import core.result_viewer as rv


def test_bridge_project_token_roundtrip(monkeypatch):
    monkeypatch.setattr(rv, "_get_file_token_secret", lambda: b"unit-test-bridge-file-secret")
    tok = rv.create_bridge_project_file_token("cursor", "src/foo.txt", expiry_sec=3600)
    assert tok and len(tok) >= 33
    got = rv.verify_bridge_project_file_token(tok)
    assert got == ("cursor", "src/foo.txt", "", "")


def test_bridge_project_token_claude_backend(monkeypatch):
    monkeypatch.setattr(rv, "_get_file_token_secret", lambda: b"unit-test-bridge-file-secret")
    tok = rv.create_bridge_project_file_token("claude", "README.md")
    got = rv.verify_bridge_project_file_token(tok)
    assert got == ("claude", "README.md", "", "")


def test_bridge_project_token_includes_friend_scope(monkeypatch):
    monkeypatch.setattr(rv, "_get_file_token_secret", lambda: b"unit-test-bridge-file-secret")
    tok = rv.create_bridge_project_file_token(
        "cursor",
        "src/foo.txt",
        expiry_sec=3600,
        user_id="u1",
        friend_id="proj-a",
    )
    got = rv.verify_bridge_project_file_token(tok)
    assert got == ("cursor", "src/foo.txt", "u1", "proj-a")


def test_build_bridge_project_browser_url_requires_base(monkeypatch):
    monkeypatch.setattr(rv, "_get_file_token_secret", lambda: b"secret")
    monkeypatch.setattr(rv, "resolve_file_link_base_url", lambda _pref=None: "")
    url, err = rv.build_bridge_project_browser_url("cursor", "a.txt")
    assert url is None
    assert err and "core_public_url" in err.lower()


def test_build_bridge_project_browser_url_signed(monkeypatch):
    monkeypatch.setattr(rv, "_get_file_token_secret", lambda: b"secret")
    monkeypatch.setattr(rv, "resolve_file_link_base_url", lambda _pref=None: "https://core.example")
    url, err = rv.build_bridge_project_browser_url("cursor", "lib/x.dart")
    assert err is None
    assert url
    assert url.startswith("https://core.example/files/bridge-project?token=")


def test_validate_bridge_project_rel_path_rejects_traversal():
    assert rv.validate_bridge_project_rel_path("cursor", "../etc/passwd") is False
    assert rv.validate_bridge_project_rel_path("cursor", "ok/sub.txt") is True
