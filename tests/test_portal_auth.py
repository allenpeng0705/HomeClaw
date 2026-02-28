"""
Tests for Portal admin auth (Step 3): set_admin, verify_portal_admin, admin_is_configured.
Uses temp dir for portal_admin.yml; env override tested without file.
"""
import os
from pathlib import Path

import pytest


@pytest.fixture
def temp_admin_file(monkeypatch, tmp_path):
    """Point portal auth to tmp_path for portal_admin.yml."""
    admin_file = tmp_path / "portal_admin.yml"
    import portal.config as mod
    monkeypatch.setattr(mod, "get_config_dir", lambda: tmp_path)
    import portal.auth as auth_mod
    monkeypatch.setattr(auth_mod, "get_config_dir", lambda: tmp_path)
    return admin_file


def test_admin_is_configured_false_when_no_file(temp_admin_file):
    from portal import auth
    assert auth.admin_is_configured() is False


def test_set_admin_creates_file(temp_admin_file):
    from portal import auth
    ok = auth.set_admin("admin", "secret123")
    assert ok is True
    assert temp_admin_file.exists()
    assert "admin_username" in temp_admin_file.read_text()


def test_verify_after_set_succeeds(temp_admin_file):
    from portal import auth
    auth.set_admin("admin", "secret123")
    assert auth.verify_portal_admin("admin", "secret123") is True
    assert auth.verify_portal_admin("admin", "wrong") is False
    assert auth.verify_portal_admin("wrong", "secret123") is False


def test_admin_is_configured_true_after_set(temp_admin_file):
    from portal import auth
    auth.set_admin("u", "p")
    assert auth.admin_is_configured() is True


def test_set_admin_rejects_empty(temp_admin_file):
    from portal import auth
    assert auth.set_admin("", "p") is False
    assert auth.set_admin("u", "") is False


def test_verify_rejects_empty(temp_admin_file):
    from portal import auth
    auth.set_admin("u", "p")
    assert auth.verify_portal_admin("", "p") is False
    assert auth.verify_portal_admin("u", "") is False
