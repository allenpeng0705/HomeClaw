"""Tests for Portal session cookie: create_session_value, verify_session_value."""
import time

import pytest

from portal.session import create_session_value, verify_session_value


def test_create_and_verify_session():
    v = create_session_value("admin")
    assert v
    user = verify_session_value(v)
    assert user == "admin"


def test_verify_expired_session():
    import portal.session as mod
    # Create with short TTL and expire
    old_ttl = mod.SESSION_TTL_SECONDS
    mod.SESSION_TTL_SECONDS = -1
    try:
        v = create_session_value("admin")
        user = verify_session_value(v)
        assert user is None
    finally:
        mod.SESSION_TTL_SECONDS = old_ttl


def test_verify_invalid_returns_none():
    assert verify_session_value("") is None
    assert verify_session_value("bad") is None
    assert verify_session_value("x:y:z") is None
