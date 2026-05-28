"""
Hierarchical Tool Policy System (inspired by OpenClaw)

Implements a multi-layer policy resolution system where policies can be defined at:
1. Global level - system-wide defaults
2. Agent level - per-friend/agent overrides
3. Provider level - model/provider-specific rules
4. Group level - chat/group-specific policies  
5. Subagent level - special rules for nested agents

Policies support:
- Allow/Deny lists (tool names or groups)
- Profile-based tool filtering
- Risk tier restrictions
- Inheritance from parent sessions
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

from loguru import logger

from base.tool_profiles import (
    TOOL_PROFILES,
    TOOL_GROUPS,
    get_tool_names_for_profile,
    expand_groups_to_tool_names,
    VALID_PROFILES,
)
from base.tools import ToolDefinition


@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule."""
    effect: str  # "allow" or "deny"
    tools: List[str]  # tool names or group references (e.g., "group:fs")
    condition: Optional[str] = None  # Optional condition expression


@dataclass(frozen=True)
class ToolPolicy:
    """A complete tool policy configuration."""
    name: str
    description: str = ""
    allow: List[str] = field(default_factory=list)  # tool names or groups
    deny: List[str] = field(default_factory=list)   # tool names or groups
    profile: Optional[str] = None  # profile name (full, minimal, messaging, coding)
    priority: int = 0  # higher = evaluated first
    inherited: bool = False  # whether this policy inherits from parent


@dataclass(frozen=True)
class PolicyContext:
    """Context for policy evaluation."""
    user_id: Optional[str] = None
    friend_id: Optional[str] = None
    channel_type: Optional[str] = None
    group_id: Optional[str] = None
    subagent_depth: int = 0  # 0 = root agent, 1+ = subagent level
    provider_name: Optional[str] = None
    session_id: Optional[str] = None
    parent_policy: Optional['ToolPolicy'] = None


class PolicyResolutionResult:
    """Result of policy evaluation for a tool."""
    
    def __init__(self, allowed: bool, tool_name: str, policy_name: str, reason: str = ""):
        self.allowed = allowed
        self.tool_name = tool_name
        self.policy_name = policy_name
        self.reason = reason
    
    def __repr__(self):
        return f"PolicyResolutionResult(allowed={self.allowed}, tool={self.tool_name}, policy={self.policy_name})"


class ToolPolicyEngine:
    """
    Engine for resolving tool access through hierarchical policy layers.
    
    Policy evaluation order (highest to lowest priority):
    1. Subagent Policy (depth-based restrictions)
    2. Group Policy (chat/group-specific)
    3. Agent Policy (friend/agent-specific)
    4. Provider Policy (model/provider-specific)
    5. Global Policy (system-wide defaults)
    
    Within each policy, deny rules are evaluated before allow rules.
    """
    
    def __init__(self):
        self.policies: Dict[str, ToolPolicy] = {}
        self._subagent_deny_list: Set[str] = set()  # Always denied for subagents
        self._subagent_leaf_deny_list: Set[str] = set()  # Denied for leaf subagents
    
    def register_policy(self, policy: ToolPolicy) -> None:
        """Register a policy by name."""
        self.policies[policy.name] = policy
    
    def unregister_policy(self, name: str) -> bool:
        """Remove a policy by name."""
        if name in self.policies:
            del self.policies[name]
            return True
        return False
    
    def set_subagent_restrictions(
        self,
        always_deny: Optional[List[str]] = None,
        leaf_deny: Optional[List[str]] = None,
    ) -> None:
        """
        Set subagent tool restrictions.
        
        always_deny: Tools always denied for any subagent
        leaf_deny: Tools denied for leaf subagents (non-orchestrators)
        """
        if always_deny:
            self._subagent_deny_list = set(always_deny)
        if leaf_deny:
            self._subagent_leaf_deny_list = set(leaf_deny)
    
    def _expand_tool_list(self, tools: List[str]) -> Set[str]:
        """Expand a list of tools/groups to a flat set of tool names."""
        expanded = expand_groups_to_tool_names(tools, TOOL_GROUPS)
        return set(expanded)
    
    def _evaluate_single_policy(
        self,
        tool_name: str,
        policy: ToolPolicy,
        context: PolicyContext,
    ) -> Optional[PolicyResolutionResult]:
        """
        Evaluate a single policy for a tool.
        Returns None if policy doesn't apply, otherwise returns result.
        """
        # First check profile restriction
        if policy.profile and policy.profile in VALID_PROFILES:
            profile_tools = get_tool_names_for_profile(policy.profile, TOOL_PROFILES)
            if tool_name not in profile_tools:
                return PolicyResolutionResult(
                    allowed=False,
                    tool_name=tool_name,
                    policy_name=policy.name,
                    reason=f"tool not in profile '{policy.profile}'"
                )
        
        # Expand deny list and check
        deny_tools = self._expand_tool_list(policy.deny)
        if tool_name in deny_tools:
            return PolicyResolutionResult(
                allowed=False,
                tool_name=tool_name,
                policy_name=policy.name,
                reason="tool in deny list"
            )
        
        # Expand allow list and check
        allow_tools = self._expand_tool_list(policy.allow)
        if allow_tools:  # If allow list is non-empty, tool must be in it
            if tool_name not in allow_tools:
                return PolicyResolutionResult(
                    allowed=False,
                    tool_name=tool_name,
                    policy_name=policy.name,
                    reason="tool not in allow list"
                )
        
        # Policy doesn't explicitly deny or restrict
        return None
    
    def _evaluate_subagent_rules(
        self,
        tool_name: str,
        context: PolicyContext,
    ) -> Optional[PolicyResolutionResult]:
        """
        Evaluate subagent-specific rules.
        
        Orchestrator subagents (depth > 0 but can spawn children) have fewer restrictions.
        Leaf subagents (depth > 0 and cannot spawn) have more restrictions.
        """
        if context.subagent_depth == 0:
            return None  # Not a subagent
        
        # Always denied for any subagent
        if tool_name in self._subagent_deny_list:
            return PolicyResolutionResult(
                allowed=False,
                tool_name=tool_name,
                policy_name="subagent_global",
                reason="tool always denied for subagents"
            )
        
        # Denied for leaf subagents (non-orchestrators)
        # We consider depth > 1 as leaf (grandchildren) or check for orchestrator flag
        if context.subagent_depth > 1:
            if tool_name in self._subagent_leaf_deny_list:
                return PolicyResolutionResult(
                    allowed=False,
                    tool_name=tool_name,
                    policy_name="subagent_leaf",
                    reason="tool denied for leaf subagents"
                )
        
        return None
    
    def evaluate(
        self,
        tool_name: str,
        context: PolicyContext,
        policy_hierarchy: Optional[List[str]] = None,
    ) -> PolicyResolutionResult:
        """
        Evaluate tool access through the policy hierarchy.
        
        policy_hierarchy: Optional list of policy names to evaluate in order.
                         If not provided, uses default hierarchy.
        """
        # Check subagent rules first
        subagent_result = self._evaluate_subagent_rules(tool_name, context)
        if subagent_result is not None:
            return subagent_result
        
        # Build evaluation order
        if policy_hierarchy:
            policies_to_evaluate = policy_hierarchy
        else:
            # Default hierarchy: subagent -> group -> agent -> provider -> global
            policies_to_evaluate = []
            
            # Group policy
            if context.group_id:
                group_policy_name = f"group_{context.group_id}"
                if group_policy_name in self.policies:
                    policies_to_evaluate.append(group_policy_name)
            
            # Agent/Friend policy
            if context.friend_id:
                agent_policy_name = f"agent_{context.friend_id}"
                if agent_policy_name in self.policies:
                    policies_to_evaluate.append(agent_policy_name)
            
            # Provider policy
            if context.provider_name:
                provider_policy_name = f"provider_{context.provider_name}"
                if provider_policy_name in self.policies:
                    policies_to_evaluate.append(provider_policy_name)
            
            # Global policy
            if "global" in self.policies:
                policies_to_evaluate.append("global")
        
        # Sort by priority within hierarchy
        policies_to_evaluate.sort(
            key=lambda name: self.policies.get(name, ToolPolicy(name="")).priority,
            reverse=True
        )
        
        # Evaluate each policy
        for policy_name in policies_to_evaluate:
            policy = self.policies.get(policy_name)
            if not policy:
                continue
            
            result = self._evaluate_single_policy(tool_name, policy, context)
            if result is not None:
                return result
        
        # If no policy denies, allow by default
        return PolicyResolutionResult(
            allowed=True,
            tool_name=tool_name,
            policy_name="default",
            reason="no restrictive policy matched"
        )
    
    def evaluate_many(
        self,
        tool_names: List[str],
        context: PolicyContext,
        policy_hierarchy: Optional[List[str]] = None,
    ) -> Dict[str, PolicyResolutionResult]:
        """Evaluate multiple tools at once."""
        results = {}
        for tool_name in tool_names:
            results[tool_name] = self.evaluate(tool_name, context, policy_hierarchy)
        return results

    def filter_tools(
        self,
        tools: List[ToolDefinition],
        context: PolicyContext,
        policy_hierarchy: Optional[List[str]] = None,
    ) -> List[ToolDefinition]:
        """
        Filter a list of tools based on policy evaluation.

        Returns only tools that are allowed by the policy engine.
        """
        allowed = []
        for tool in tools:
            tool_name = getattr(tool, "name", None)
            if not tool_name:
                continue
            result = self.evaluate(tool_name, context, policy_hierarchy)
            if result.allowed:
                allowed.append(tool)
        return allowed


# Global policy engine instance
_policy_engine: Optional[ToolPolicyEngine] = None


def get_policy_engine() -> ToolPolicyEngine:
    """Return the global policy engine, initializing with defaults if needed."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = ToolPolicyEngine()
        # Initialize with default subagent restrictions (OpenClaw-inspired)
        _policy_engine.set_subagent_restrictions(
            always_deny=[
                "gateway",
                "agents_list",
                "session_status",
                "cron",
                "sessions_send",
            ],
            leaf_deny=[
                "subagents",
                "sessions_list",
                "sessions_history",
                "sessions_spawn",
            ]
        )
        # Add default global policy (allow all)
        _policy_engine.register_policy(ToolPolicy(
            name="global",
            description="System-wide default policy",
            allow=[],  # Empty = allow all not explicitly denied
            deny=[],
            priority=0,
        ))
    return _policy_engine


def reset_policy_engine() -> None:
    """Reset the policy engine (for testing)."""
    global _policy_engine
    _policy_engine = None


# Helper functions for common operations

def build_policy_from_config(config: Dict[str, Any]) -> ToolPolicy:
    """Build a ToolPolicy from a config dictionary."""
    return ToolPolicy(
        name=config.get("name", "unnamed"),
        description=config.get("description", ""),
        allow=config.get("allow", []),
        deny=config.get("deny", []),
        profile=config.get("profile"),
        priority=config.get("priority", 0),
        inherited=config.get("inherited", False),
    )


def get_policy_context_from_request(request: Any) -> PolicyContext:
    """Extract policy context from a request object."""
    user_id = getattr(request, "user_id", None)
    friend_id = getattr(request, "friend_id", None)
    channel_type = getattr(request, "channelType", None)
    if channel_type is not None:
        channel_type = str(channel_type).split(".")[-1]
    
    # Extract subagent depth from metadata
    subagent_depth = 0
    try:
        md = getattr(request, "request_metadata", None) or {}
        if isinstance(md, dict):
            subagent_depth = int(md.get("subagent_depth", 0))
    except Exception:
        pass
    
    return PolicyContext(
        user_id=str(user_id).strip() if user_id else None,
        friend_id=str(friend_id).strip() if friend_id else None,
        channel_type=str(channel_type).strip() if channel_type else None,
        subagent_depth=subagent_depth,
    )


def initialize_policy_engine_from_config(policies_config: List[Dict[str, Any]]) -> None:
    """
    Initialize the global policy engine with policies from config.

    Expected config format:
    [
        {"name": "global", "description": "...", "allow": [], "deny": [], "priority": 0},
        {"name": "agent_MyFriend", "description": "...", "allow": ["file_read"], "deny": ["exec"], "priority": 10},
        ...
    ]
    """
    engine = get_policy_engine()
    for policy_config in policies_config:
        if not isinstance(policy_config, dict):
            continue
        policy_name = policy_config.get("name")
        if not policy_name:
            continue
        try:
            policy = build_policy_from_config(policy_config)
            engine.register_policy(policy)
        except Exception as e:
            logger.warning(f"Failed to register policy '{policy_name}': {e}")
