"""
Approval system — Phase 5: Per-tool approval policies, state machine, delivery.

Usage:
    from core.approvals import build_policy_from_config, create_request

    policy = build_policy_from_config({"tools": {"exec_shell": {"policy": "ask"}}})
    req = create_request("exec_shell", tool_args={"command": "git push"},
                         policy=policy, owner_user_id="u1")
    if req.state == ApprovalState.PENDING:
        # deliver to channel, wait for operator response
        resolved = resolve_request(req.approval_id, ApprovalState.APPROVED, "operator")
"""

from core.approvals.policy import (
    ApprovalDecision, ApprovalState, ApprovalRule, ApprovalPolicy,
    ApprovalRequest, build_policy_from_config, resolve_approval,
)
from core.approvals.state import (
    create_request, resolve_request, get_pending, list_pending,
    expire_stale, clear_for_test,
)

__all__ = [
    "ApprovalDecision", "ApprovalState", "ApprovalRule", "ApprovalPolicy",
    "ApprovalRequest", "build_policy_from_config", "resolve_approval",
    "create_request", "resolve_request", "get_pending", "list_pending",
    "expire_stale", "clear_for_test",
]
