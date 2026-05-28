"""Tests for core.approvals — Phase 5: Approval system enhancement."""

from __future__ import annotations

from core.approvals import (
    ApprovalDecision, ApprovalState, ApprovalRule, ApprovalPolicy,
    ApprovalRequest,
    build_policy_from_config, resolve_approval,
    create_request, resolve_request, get_pending, list_pending,
    expire_stale, clear_for_test,
)


class TestPolicy:
    """Approval policy engine."""

    def test_default_policy(self):
        p = ApprovalPolicy()
        assert p.resolve("any_tool") == ApprovalDecision.ASK

    def test_allow_all(self):
        p = ApprovalPolicy(default=ApprovalDecision.ALLOW)
        assert p.resolve("any_tool") == ApprovalDecision.ALLOW

    def test_deny_all(self):
        p = ApprovalPolicy(default=ApprovalDecision.DENY)
        assert p.resolve("any_tool") == ApprovalDecision.DENY

    def test_specific_rule(self):
        p = ApprovalPolicy(rules=[
            ApprovalRule(tool_name="exec_shell", decision=ApprovalDecision.ASK),
            ApprovalRule(tool_name="file_read", decision=ApprovalDecision.ALLOW),
        ])
        assert p.resolve("exec_shell") == ApprovalDecision.ASK
        assert p.resolve("file_read") == ApprovalDecision.ALLOW
        assert p.resolve("unknown") == ApprovalDecision.ASK

    def test_wildcard_rule(self):
        p = ApprovalPolicy(rules=[
            ApprovalRule(tool_name="*", decision=ApprovalDecision.DENY),
            ApprovalRule(tool_name="file_read", decision=ApprovalDecision.ALLOW),
        ])
        assert p.resolve("exec_shell") == ApprovalDecision.DENY
        assert p.resolve("file_read") == ApprovalDecision.ALLOW  # specific overrides wildcard

    def test_conditional_path(self):
        p = ApprovalPolicy(rules=[
            ApprovalRule(tool_name="exec_shell", decision=ApprovalDecision.DENY,
                         condition_path=r"^/etc/"),
            ApprovalRule(tool_name="exec_shell", decision=ApprovalDecision.ALLOW,
                         condition_path=r"^/home/"),
        ])
        assert p.resolve("exec_shell", path="/etc/passwd") == ApprovalDecision.DENY
        assert p.resolve("exec_shell", path="/home/user/script.sh") == ApprovalDecision.ALLOW
        assert p.resolve("exec_shell", path="/tmp/thing") == ApprovalDecision.ASK  # default

    def test_conditional_command(self):
        p = ApprovalPolicy(rules=[
            ApprovalRule(tool_name="exec_shell", decision=ApprovalDecision.DENY,
                         condition_command=r"\brm\b"),
        ])
        assert p.resolve("exec_shell", command="rm -rf /") == ApprovalDecision.DENY
        assert p.resolve("exec_shell", command="ls -la") == ApprovalDecision.ASK

    def test_build_from_config(self):
        config = {
            "default": "allow",
            "tools": {
                "exec_shell": {"policy": "ask", "reason": "Shell access requires approval"},
                "file_write": {"policy": "deny", "path": r"^/etc/"},
                "file_read": {"policy": "allow"},
            },
        }
        p = build_policy_from_config(config)
        assert p.default == ApprovalDecision.ALLOW
        assert p.resolve("exec_shell") == ApprovalDecision.ASK
        assert p.resolve("file_write", path="/etc/hosts") == ApprovalDecision.DENY
        assert p.resolve("file_read") == ApprovalDecision.ALLOW
        assert p.resolve("unknown") == ApprovalDecision.ALLOW

    def test_build_from_none(self):
        p = build_policy_from_config(None)
        assert p.default == ApprovalDecision.ASK

    def test_resolve_approval_helper(self):
        p = ApprovalPolicy(default=ApprovalDecision.DENY)
        assert resolve_approval(p, "any") == ApprovalDecision.DENY


class TestStateMachine:
    """Approval state machine."""

    def setup_method(self):
        clear_for_test()

    def test_create_auto_allow(self):
        policy = ApprovalPolicy(default=ApprovalDecision.ALLOW)
        req = create_request("file_read", policy=policy, owner_user_id="u1")
        assert req.state == ApprovalState.APPROVED

    def test_create_auto_deny(self):
        policy = ApprovalPolicy(default=ApprovalDecision.DENY)
        req = create_request("exec_shell", policy=policy)
        assert req.state == ApprovalState.DENIED

    def test_create_pending(self):
        policy = ApprovalPolicy(default=ApprovalDecision.ASK)
        req = create_request("exec_shell", policy=policy, owner_user_id="u1")
        assert req.state == ApprovalState.PENDING
        assert req.owner_user_id == "u1"

    def test_resolve_approve(self):
        policy = ApprovalPolicy(default=ApprovalDecision.ASK)
        req = create_request("exec_shell", policy=policy, owner_user_id="u1")
        resolved = resolve_request(req.approval_id, ApprovalState.APPROVED, "operator")
        assert resolved is not None
        assert resolved.state == ApprovalState.APPROVED
        assert resolved.resolved_by == "operator"

    def test_resolve_deny(self):
        policy = ApprovalPolicy(default=ApprovalDecision.ASK)
        req = create_request("exec_shell", policy=policy)
        resolved = resolve_request(req.approval_id, ApprovalState.DENIED)
        assert resolved.state == ApprovalState.DENIED

    def test_resolve_nonexistent(self):
        assert resolve_request("nonexistent", ApprovalState.APPROVED) is None

    def test_get_pending(self):
        req = create_request("exec_shell", owner_user_id="u1")
        found = get_pending(req.approval_id)
        assert found is not None
        assert found.tool_name == "exec_shell"

    def test_list_pending_filtered(self):
        create_request("tool_a", owner_user_id="u1")
        create_request("tool_b", owner_user_id="u2")
        create_request("tool_c", owner_user_id="u1")
        u1_pending = list_pending(owner_user_id="u1")
        assert len(u1_pending) == 2
        all_pending = list_pending()
        assert len(all_pending) == 3

    def test_expire_stale(self):
        req = create_request("tool_x", ttl_seconds=1)
        import time
        time.sleep(1.1)
        expired = expire_stale(ttl_seconds=1)
        assert len(expired) == 1
        assert expired[0].state == ApprovalState.TIMED_OUT
        assert get_pending(req.approval_id) is None


class TestApprovalRequest:
    """ApprovalRequest dataclass."""

    def test_defaults(self):
        r = ApprovalRequest(approval_id="a1", tool_name="test")
        assert r.state == ApprovalState.PENDING
        assert r.decision == ApprovalDecision.ASK
        assert r.tool_args == {}

    def test_metadata(self):
        r = ApprovalRequest(approval_id="a1", tool_name="test",
                            metadata={"command": "ls", "cwd": "/tmp"})
        assert r.metadata["command"] == "ls"
