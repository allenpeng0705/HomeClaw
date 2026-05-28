"""
Approval state machine — Phase 5: tracks pending approvals with timeout and resolution.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from core.approvals.policy import (
    ApprovalDecision, ApprovalState, ApprovalRequest, ApprovalPolicy,
)


# In-memory store for pending approvals
_pending: Dict[str, ApprovalRequest] = {}


def create_request(
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    *,
    owner_user_id: str = "",
    owner_session_key: str = "",
    channel_name: str = "",
    ttl_seconds: int = 1800,
    policy: Optional[ApprovalPolicy] = None,
) -> ApprovalRequest:
    """Create a new approval request. If policy decides ALLOW/DENY, resolves immediately."""
    decision = ApprovalDecision.ASK
    if policy is not None:
        decision = policy.resolve(tool_name)

    req = ApprovalRequest(
        approval_id=str(uuid.uuid4()),
        tool_name=tool_name,
        tool_args=tool_args or {},
        decision=decision,
        state=ApprovalState.APPROVED if decision == ApprovalDecision.ALLOW else
              ApprovalState.DENIED if decision == ApprovalDecision.DENY else
              ApprovalState.PENDING,
        owner_user_id=owner_user_id,
        owner_session_key=owner_session_key,
        channel_name=channel_name,
        created_at=time.time(),
        ttl_seconds=ttl_seconds,
    )

    if req.state == ApprovalState.PENDING:
        _pending[req.approval_id] = req
        logger.debug("Approval pending: {} for tool '{}'", req.approval_id, tool_name)
    else:
        logger.debug("Approval auto-resolved: {} → {} for '{}'",
                     req.approval_id, req.state.value, tool_name)

    return req


def resolve_request(approval_id: str, state: ApprovalState,
                    resolved_by: str = "") -> Optional[ApprovalRequest]:
    """Resolve a pending approval."""
    req = _pending.pop(approval_id, None)
    if req is None:
        return None
    req.state = state
    req.resolved_at = time.time()
    req.resolved_by = resolved_by
    logger.info("Approval {} {} by '{}'", approval_id, state.value, resolved_by)
    return req


def get_pending(approval_id: str) -> Optional[ApprovalRequest]:
    """Get a pending approval by id."""
    return _pending.get(approval_id)


def list_pending(owner_user_id: str = "") -> List[ApprovalRequest]:
    """List all pending approvals, optionally filtered by owner."""
    if owner_user_id:
        return [r for r in _pending.values() if r.owner_user_id == owner_user_id]
    return list(_pending.values())


def expire_stale(ttl_seconds: int = 1800) -> List[ApprovalRequest]:
    """Expire and remove stale pending approvals. Returns expired requests."""
    now = time.time()
    expired: List[ApprovalRequest] = []
    for aid in list(_pending.keys()):
        req = _pending[aid]
        if now - req.created_at > max(req.ttl_seconds, ttl_seconds):
            expired.append(req)
            req.state = ApprovalState.TIMED_OUT
            req.resolved_at = now
            del _pending[aid]
            logger.debug("Approval {} timed out", aid)
    return expired


def clear_for_test() -> None:
    _pending.clear()
