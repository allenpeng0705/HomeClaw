"""
Approval policy engine — Phase 5: Per-tool approval policies.

Inspired by OpenClaw's operator approval and exec-approval systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ApprovalDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRule:
    tool_name: str
    decision: ApprovalDecision = ApprovalDecision.ASK
    reason: str = ""

    # Conditional: only ask when these conditions match
    condition_path: Optional[str] = None           # regex on file path
    condition_command: Optional[str] = None        # regex on shell command
    condition_session_key: Optional[str] = None    # match session key


@dataclass
class ApprovalPolicy:
    """Collection of per-tool approval rules."""
    default: ApprovalDecision = ApprovalDecision.ASK
    rules: List[ApprovalRule] = field(default_factory=list)

    def resolve(self, tool_name: str, *, path: str = "",
                command: str = "", session_key: str = "") -> ApprovalDecision:
        """Resolve the approval decision for a tool call. Specific rules override wildcards."""
        import re

        # Check specific rules first, then wildcards
        for rule in self.rules:
            if rule.tool_name != tool_name:
                continue
            if rule.condition_path and not re.search(rule.condition_path, path):
                continue
            if rule.condition_command and not re.search(rule.condition_command, command):
                continue
            if rule.condition_session_key and rule.condition_session_key != session_key:
                continue
            return rule.decision

        # Fall back to wildcard rules
        for rule in self.rules:
            if rule.tool_name != "*":
                continue
            if rule.condition_path and not re.search(rule.condition_path, path):
                continue
            if rule.condition_command and not re.search(rule.condition_command, command):
                continue
            return rule.decision

        return self.default


@dataclass
class ApprovalRequest:
    approval_id: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    decision: ApprovalDecision = ApprovalDecision.ASK
    state: ApprovalState = ApprovalState.PENDING
    owner_user_id: str = ""
    owner_session_key: str = ""
    channel_name: str = ""
    created_at: float = 0.0
    ttl_seconds: int = 1800
    resolved_at: Optional[float] = None
    resolved_by: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def build_policy_from_config(config: Optional[Dict[str, Any]]) -> ApprovalPolicy:
    """Build an ApprovalPolicy from a config dict."""
    if not isinstance(config, dict):
        return ApprovalPolicy()

    default_str = config.get("default", "ask")
    try:
        default = ApprovalDecision(default_str)
    except ValueError:
        default = ApprovalDecision.ASK

    rules: List[ApprovalRule] = []
    tools_cfg = config.get("tools")
    if isinstance(tools_cfg, dict):
        for tool_name, rule_cfg in tools_cfg.items():
            if not isinstance(rule_cfg, dict):
                continue
            try:
                decision = ApprovalDecision(rule_cfg.get("policy", "ask"))
            except ValueError:
                decision = ApprovalDecision.ASK
            rules.append(ApprovalRule(
                tool_name=tool_name,
                decision=decision,
                reason=rule_cfg.get("reason", ""),
                condition_path=rule_cfg.get("path"),
                condition_command=rule_cfg.get("command"),
            ))

    return ApprovalPolicy(default=default, rules=rules)


def resolve_approval(policy: ApprovalPolicy, tool_name: str,
                     *, path: str = "", command: str = "",
                     session_key: str = "") -> ApprovalDecision:
    return policy.resolve(tool_name, path=path, command=command,
                          session_key=session_key)
