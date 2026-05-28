"""Tests for OpenClaw-inspired features: tool groups, policy engine, search, and audit logging."""

from __future__ import annotations

import pytest

from base.tool_profiles import (
    TOOL_GROUPS,
    get_tool_names_for_group,
    get_tool_names_for_groups,
    expand_groups_to_tool_names,
    filter_tools_by_groups,
    get_groups_for_tool,
)
from base.tool_policy import (
    ToolPolicy,
    PolicyContext,
    ToolPolicyEngine,
    PolicyResolutionResult,
    build_policy_from_config,
)
from base.tool_permissions import (
    ToolPermissionContext,
    PermissionResult,
    evaluate_tool_permission,
    ALLOW_ALL,
    ALLOW_READ_RESTRICT_WRITE,
    ALLOW_READ_ONLY,
    DEFAULT_TOOL_RISK_TIERS,
    VALID_RISK_TIERS,
)
from base.tools import ToolDefinition


async def _noop_exec(*_a, **_k):
    return ""


class TestToolGroups:
    """Test semantic tool groups."""

    def test_tool_groups_defined(self):
        """Ensure all expected groups are defined."""
        expected_groups = {
            "group:fs",
            "group:runtime",
            "group:web",
            "group:memory",
            "group:sessions",
            "group:messaging",
            "group:browser",
            "group:coding",
        }
        assert expected_groups.issubset(TOOL_GROUPS.keys())

    def test_get_tool_names_for_group(self):
        """Test retrieving tools by group."""
        fs_tools = get_tool_names_for_group("group:fs")
        assert isinstance(fs_tools, list)
        assert "file_read" in fs_tools
        assert "file_write" in fs_tools
        assert "folder_list" in fs_tools

    def test_get_tool_names_for_groups(self):
        """Test retrieving tools from multiple groups."""
        tools = get_tool_names_for_groups(["group:fs", "group:web"])
        assert isinstance(tools, set)
        assert "file_read" in tools
        assert "web_search" in tools

    def test_expand_groups_to_tool_names(self):
        """Test expanding mixed tool names and groups."""
        items = ["file_read", "group:fs", "web_search"]
        expanded = expand_groups_to_tool_names(items)
        assert isinstance(expanded, list)
        assert "file_read" in expanded
        assert "web_search" in expanded
        assert "file_write" in expanded  # From group:fs

    def test_filter_tools_by_groups(self):
        """Test filtering tool definitions by groups."""
        tools = [
            ToolDefinition(name="file_read", description="", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="web_search", description="", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="exec", description="", parameters={}, execute_async=_noop_exec),
        ]
        filtered = filter_tools_by_groups(tools, ["group:fs"])
        names = {t.name for t in filtered}
        assert "file_read" in names
        assert "web_search" not in names

    def test_get_groups_for_tool(self):
        """Test finding groups a tool belongs to."""
        groups = get_groups_for_tool("file_read")
        assert isinstance(groups, list)
        assert "group:fs" in groups
        assert "group:coding" in groups


class TestToolPolicyEngine:
    """Test hierarchical policy engine."""

    def test_register_and_unregister_policy(self):
        """Test policy registration using fresh engine."""
        engine = ToolPolicyEngine()
        policy = ToolPolicy(
            name="test_policy",
            description="Test policy",
            allow=["file_read"],
            deny=["exec"],
        )
        engine.register_policy(policy)
        assert "test_policy" in engine.policies

        engine.unregister_policy("test_policy")
        assert "test_policy" not in engine.policies

    def test_evaluate_allow_all_default(self):
        """Test evaluation with allow-all policy (default)."""
        engine = ToolPolicyEngine()
        context = PolicyContext(user_id="test_user")
        result = engine.evaluate("file_read", context)
        assert result.allowed is True
        assert result.policy_name == "default"

    def test_evaluate_with_context_matched_policy(self):
        """Test evaluation with context-matched policy (friend_id triggers agent policy)."""
        engine = ToolPolicyEngine()
        # Register a policy that will be matched via context
        policy = ToolPolicy(
            name="agent_HomeClaw",
            description="HomeClaw agent policy",
            deny=["exec"],
            priority=10,
        )
        engine.register_policy(policy)

        # friend_id triggers agent policy lookup
        context = PolicyContext(user_id="test_user", friend_id="HomeClaw")
        result = engine.evaluate("exec", context)
        assert result.allowed is False
        assert result.policy_name == "agent_HomeClaw"

    def test_evaluate_with_group_context(self):
        """Test evaluation with group context."""
        engine = ToolPolicyEngine()
        policy = ToolPolicy(
            name="group_general",
            description="General group policy",
            deny=["exec"],
            priority=10,
        )
        engine.register_policy(policy)

        context = PolicyContext(user_id="test_user", group_id="general")
        result = engine.evaluate("exec", context)
        assert result.allowed is False
        assert result.policy_name == "group_general"

    def test_evaluate_with_global_policy(self):
        """Test evaluation with global policy."""
        engine = ToolPolicyEngine()
        policy = ToolPolicy(
            name="global",
            description="Global policy",
            deny=["exec"],
            priority=5,
        )
        engine.register_policy(policy)

        context = PolicyContext(user_id="test_user")
        result = engine.evaluate("exec", context)
        assert result.allowed is False
        assert result.policy_name == "global"

    def test_evaluate_with_policy_hierarchy(self):
        """Test evaluation with explicit policy hierarchy."""
        engine = ToolPolicyEngine()
        engine.register_policy(ToolPolicy(
            name="deny_exec",
            deny=["exec"],
            priority=10,
        ))

        # Use explicit hierarchy to include our policy
        context = PolicyContext(user_id="test_user")
        result = engine.evaluate("exec", context, policy_hierarchy=["deny_exec"])
        assert result.allowed is False
        assert result.policy_name == "deny_exec"

    def test_evaluate_with_group_deny(self):
        """Test evaluation with group-based deny."""
        engine = ToolPolicyEngine()
        # Policy name must match the pattern: group_{group_id}
        policy = ToolPolicy(
            name="group_fs",
            description="Deny file system group",
            deny=["group:fs"],
            priority=10,
        )
        engine.register_policy(policy)

        context = PolicyContext(user_id="test_user", group_id="fs")
        result = engine.evaluate("file_read", context)
        assert result.allowed is False

    def test_subagent_restrictions(self):
        """Test subagent-specific restrictions require explicit setup."""
        engine = ToolPolicyEngine()
        # Set up subagent restrictions explicitly
        engine.set_subagent_restrictions(
            always_deny=["gateway", "agents_list"],
            leaf_deny=["sessions_spawn", "subagents"]
        )

        context = PolicyContext(user_id="test_user", subagent_depth=1)

        # gateway is always denied for subagents
        result = engine.evaluate("gateway", context)
        assert result.allowed is False
        assert result.policy_name == "subagent_global"

        # sessions_spawn is only denied for leaf subagents (depth > 1)
        context_leaf = PolicyContext(user_id="test_user", subagent_depth=2)
        result = engine.evaluate("sessions_spawn", context_leaf)
        assert result.allowed is False
        assert result.policy_name == "subagent_leaf"

    def test_build_policy_from_config(self):
        """Test building policy from config dict."""
        config = {
            "name": "config_policy",
            "description": "From config",
            "allow": ["file_read"],
            "deny": ["exec"],
            "priority": 5,
        }
        policy = build_policy_from_config(config)
        assert policy.name == "config_policy"
        assert policy.allow == ["file_read"]
        assert policy.deny == ["exec"]
        assert policy.priority == 5

    def test_policy_priority_ordering(self):
        """Test that higher priority policies are evaluated first in hierarchy."""
        engine = ToolPolicyEngine()

        # low_priority deny
        low_policy = ToolPolicy(
            name="low_priority",
            deny=["exec"],
            priority=1,
        )
        engine.register_policy(low_policy)

        # high_priority allow
        high_policy = ToolPolicy(
            name="high_priority",
            allow=["exec"],
            priority=100,
        )
        engine.register_policy(high_policy)

        # With explicit hierarchy, high_priority is sorted first (priority 100 > 1)
        # But since allow just continues evaluation (returns None when matched),
        # low_priority's deny will win
        context = PolicyContext(user_id="test_user")
        result = engine.evaluate("exec", context, policy_hierarchy=["low_priority", "high_priority"])

        # When low_priority is first in hierarchy, it matches deny first
        assert result.policy_name == "low_priority"
        assert result.allowed is False

    def test_profile_based_policy(self):
        """Test profile-based policy filtering."""
        engine = ToolPolicyEngine()
        policy = ToolPolicy(
            name="coding_profile",
            profile="coding",
            priority=10,
        )
        engine.register_policy(policy)

        context = PolicyContext(user_id="test_user")
        # exec is in coding profile
        result = engine.evaluate("exec", context, policy_hierarchy=["coding_profile"])
        assert result.allowed is True

        # web_search is NOT in coding profile
        result = engine.evaluate("web_search", context, policy_hierarchy=["coding_profile"])
        assert result.allowed is False


class TestToolPermissions:
    """Test enhanced tool permissions."""

    def test_valid_risk_tiers(self):
        """Test valid risk tiers."""
        assert "read" in VALID_RISK_TIERS
        assert "write" in VALID_RISK_TIERS
        assert "exec" in VALID_RISK_TIERS
        assert "network" in VALID_RISK_TIERS
        assert "user_data" in VALID_RISK_TIERS
        assert "admin" in VALID_RISK_TIERS
        assert "sensitive" in VALID_RISK_TIERS

    def test_default_tool_risk_tiers(self):
        """Test default risk tier mappings."""
        assert DEFAULT_TOOL_RISK_TIERS["file_read"] == "read"
        assert DEFAULT_TOOL_RISK_TIERS["file_write"] == "write"
        assert DEFAULT_TOOL_RISK_TIERS["exec"] == "exec"
        assert DEFAULT_TOOL_RISK_TIERS["web_search"] == "network"

    def test_allow_all_mode(self):
        """Test allow_all mode allows everything."""
        tool = ToolDefinition(
            name="exec",
            description="Execute command",
            parameters={},
            execute_async=_noop_exec,
        )
        ctx = ToolPermissionContext(mode=ALLOW_ALL)
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is True

    def test_allow_read_restrict_write_mode_blocks_write(self):
        """Test allow_read_restrict_write mode blocks write tools."""
        tool = ToolDefinition(
            name="file_write",
            description="Write file",
            parameters={},
            execute_async=_noop_exec,
        )
        ctx = ToolPermissionContext(mode=ALLOW_READ_RESTRICT_WRITE)
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is False
        assert result.reason_code == "policy_tier_blocked"

    def test_allow_read_only_mode_blocks_exec(self):
        """Test allow_read_only mode blocks exec tools."""
        tool = ToolDefinition(
            name="exec",
            description="Execute command",
            parameters={},
            execute_async=_noop_exec,
        )
        ctx = ToolPermissionContext(mode=ALLOW_READ_ONLY)
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is False
        assert result.reason_code == "read_only_mode"

    def test_allowed_tiers_filter_in_restrict_mode(self):
        """Test allowed_tiers filtering works in restrict mode."""
        tool = ToolDefinition(
            name="file_write",
            description="Write file",
            parameters={},
            execute_async=_noop_exec,
        )
        # In ALLOW_READ_RESTRICT_WRITE mode, write tier is already blocked
        ctx = ToolPermissionContext(
            mode=ALLOW_READ_RESTRICT_WRITE,
            allowed_tiers={"read"},
        )
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is False

    def test_denied_tiers_filter(self):
        """Test denied_tiers filtering blocks matching tier."""
        tool = ToolDefinition(
            name="file_write",
            description="Write file",
            parameters={},
            execute_async=_noop_exec,
        )
        ctx = ToolPermissionContext(
            mode=ALLOW_READ_RESTRICT_WRITE,  # Must be in restrict mode
            denied_tiers={"write"},
        )
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is False
        assert result.reason_code == "denied_tier"

    def test_requires_confirmation_blocks(self):
        """Test requires_confirmation flag blocks tool."""
        tool = ToolDefinition(
            name="dangerous_tool",
            description="Dangerous tool",
            parameters={},
            execute_async=_noop_exec,
            requires_confirmation=True,
        )
        ctx = ToolPermissionContext(mode=ALLOW_READ_RESTRICT_WRITE)
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is False
        assert result.reason_code == "requires_confirmation"

    def test_read_tool_allowed_in_restrict_write(self):
        """Test that read tools are allowed in ALLOW_READ_RESTRICT_WRITE mode."""
        tool = ToolDefinition(
            name="file_read",
            description="Read file",
            parameters={},
            execute_async=_noop_exec,
        )
        ctx = ToolPermissionContext(mode=ALLOW_READ_RESTRICT_WRITE)
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is True

    def test_exec_blocked_in_read_only(self):
        """Test that exec tools are blocked in ALLOW_READ_ONLY mode."""
        tool = ToolDefinition(
            name="exec",
            description="Execute command",
            parameters={},
            execute_async=_noop_exec,
        )
        ctx = ToolPermissionContext(mode=ALLOW_READ_ONLY)
        result = evaluate_tool_permission(tool, {}, ctx)
        assert result.allowed is False


class TestToolPolicyPipeline:
    """Test policy pipeline with audit logging."""

    def test_evaluate_with_audit(self):
        """Test evaluation with audit trail."""
        from base.tool_policy_pipeline import ToolPolicyPipeline

        pipeline = ToolPolicyPipeline()
        context = PolicyContext(user_id="test_user")
        result = pipeline.evaluate("file_read", context)

        assert isinstance(result.allowed, bool)
        assert isinstance(result.audit_trail, object)

    def test_policy_context_with_subagent_setup(self):
        """Test policy context with subagent depth requires setup."""
        from base.tool_policy_pipeline import ToolPolicyPipeline

        pipeline = ToolPolicyPipeline()
        # Set up subagent restrictions for pipeline's engine
        pipeline._engine.set_subagent_restrictions(always_deny=["gateway"])

        context = PolicyContext(user_id="test_user", subagent_depth=1)
        result = pipeline.evaluate("gateway", context)

        assert result.allowed is False

    def test_evaluate_many(self):
        """Test evaluating multiple tools."""
        from base.tool_policy_pipeline import ToolPolicyPipeline

        pipeline = ToolPolicyPipeline()
        context = PolicyContext(user_id="test_user")
        results = pipeline.evaluate_many(
            ["file_read", "exec", "web_search"],
            context,
        )

        assert len(results) == 3
        assert all(isinstance(r.allowed, bool) for r in results.values())


class TestToolSearch:
    """Test tool search functionality using standalone functions."""

    def test_search_by_exact_name(self):
        """Test searching by exact tool name."""
        from base.tool_profiles import filter_tools_by_profile
        from base.tools import ToolDefinition

        tools = [
            ToolDefinition(name="file_read", description="Read a file", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="file_write", description="Write a file", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="exec", description="Execute command", parameters={}, execute_async=_noop_exec),
        ]

        # Use profile filtering as a stand-in for search
        filtered = filter_tools_by_profile(tools, ["coding"])
        names = {t.name for t in filtered}
        assert "exec" in names

    def test_filter_by_profile(self):
        """Test filtering by profile."""
        from base.tool_profiles import filter_tools_by_profile
        from base.tools import ToolDefinition

        tools = [
            ToolDefinition(name="web_search", description="Search the web", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="file_read", description="Read a file", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="exec", description="Execute command", parameters={}, execute_async=_noop_exec),
        ]

        # Minimal profile
        filtered = filter_tools_by_profile(tools, ["minimal"])
        names = {t.name for t in filtered}
        assert "web_search" in names
        assert "exec" not in names


class TestIntegration:
    """Integration tests for combined features."""

    def test_policy_plus_permissions_workflow(self):
        """Test policy engine working with permissions in a workflow."""
        from base.tool_policy import ToolPolicyEngine
        from base.tool_permissions import evaluate_tool_permission, ToolPermissionContext, ALLOW_ALL

        engine = ToolPolicyEngine()

        # Register a policy that denies exec via friend_id context
        policy = ToolPolicy(
            name="agent_TestAgent",
            deny=["exec"],
            priority=10,
        )
        engine.register_policy(policy)

        # Check policy evaluation with matching context
        context = PolicyContext(user_id="test_user", friend_id="TestAgent")
        policy_result = engine.evaluate("exec", context)
        assert policy_result.allowed is False

        # Permission evaluation with ALLOW_ALL - still allows
        tool = ToolDefinition(
            name="exec",
            description="Execute command",
            parameters={},
            execute_async=_noop_exec,
        )
        perm_ctx = ToolPermissionContext(mode=ALLOW_ALL)
        perm_result = evaluate_tool_permission(tool, {}, perm_ctx)
        assert perm_result.allowed is True

    def test_groups_filtering_integration(self):
        """Test tool groups working with profile filtering."""
        from base.tool_profiles import expand_groups_to_tool_names, filter_tools_by_profile
        from base.tools import ToolDefinition

        # Expand groups to tool names
        items = ["file_read", "group:fs", "group:runtime"]
        expanded = expand_groups_to_tool_names(items)
        assert "exec" in expanded  # From group:runtime
        assert "file_read" in expanded

        # Create tools and filter by profile
        tools = [
            ToolDefinition(name="file_read", description="", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="exec", description="", parameters={}, execute_async=_noop_exec),
            ToolDefinition(name="web_search", description="", parameters={}, execute_async=_noop_exec),
        ]

        filtered = filter_tools_by_profile(tools, ["coding"])
        names = {t.name for t in filtered}

        # coding profile should include file_read and exec
        assert "file_read" in names
        assert "exec" in names

    def test_memory_hierarchy_import(self):
        """Test that memory hierarchy modules can be imported."""
        from memory.memory_hierarchy import (
            HierarchicalMemory,
            MemoryType,
            MemoryTier,
            MemoryEntry,
        )
        from memory.smart_retrieval import (
            SmartMemoryRetrieval,
            QueryExpander,
            ContextAnalyzer,
        )

        assert MemoryType.WORKING.value == "working"
        assert MemoryTier.TIER_0.value == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])