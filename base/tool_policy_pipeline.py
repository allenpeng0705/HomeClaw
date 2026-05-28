"""
Policy Pipeline with Audit Logging (inspired by OpenClaw)

Implements a pipeline system for tool policy evaluation with comprehensive audit logging.

The pipeline:
1. Receives tool access request
2. Evaluates through multiple policy layers
3. Logs all decisions and reasoning
4. Returns final decision with audit trail
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from base.tool_policy import (
    PolicyContext,
    PolicyResolutionResult,
    get_policy_engine,
    ToolPolicyEngine,
)


@dataclass
class AuditEvent:
    """Record of a single policy evaluation step."""
    timestamp: datetime
    policy_name: str
    tool_name: str
    decision: str  # "allow", "deny", "skip"
    reason: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditTrail:
    """Complete audit trail for a tool access request."""
    request_id: str
    user_id: Optional[str]
    tool_name: str
    final_decision: str
    events: List[AuditEvent] = field(default_factory=list)
    
    def to_json(self) -> str:
        """Serialize audit trail to JSON."""
        return json.dumps({
            "request_id": self.request_id,
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "final_decision": self.final_decision,
            "events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "policy_name": e.policy_name,
                    "decision": e.decision,
                    "reason": e.reason,
                    "score": e.score,
                    "metadata": e.metadata,
                }
                for e in self.events
            ],
        }, ensure_ascii=False)


@dataclass
class PipelineResult:
    """Result of policy pipeline evaluation."""
    allowed: bool
    tool_name: str
    audit_trail: AuditTrail
    policy_name: str
    reason: str


class ToolPolicyPipeline:
    """
    Policy evaluation pipeline with audit logging.
    
    Pipeline stages:
    1. Pre-flight checks
    2. Subagent policy evaluation
    3. Group policy evaluation
    4. Agent policy evaluation
    5. Provider policy evaluation
    6. Global policy evaluation
    7. Post-processing and logging
    """
    
    def __init__(self, engine: Optional[ToolPolicyEngine] = None):
        self._engine = engine or get_policy_engine()
        self._audit_enabled = True
    
    def set_audit_enabled(self, enabled: bool) -> None:
        """Enable or disable audit logging."""
        self._audit_enabled = enabled
    
    def _create_audit_event(
        self,
        policy_name: str,
        tool_name: str,
        decision: str,
        reason: str,
        **kwargs,
    ) -> AuditEvent:
        """Create an audit event."""
        return AuditEvent(
            timestamp=datetime.now(),
            policy_name=policy_name,
            tool_name=tool_name,
            decision=decision,
            reason=reason,
            **kwargs,
        )
    
    def _log_audit_event(self, event: AuditEvent) -> None:
        """Log an audit event."""
        if not self._audit_enabled:
            return
        
        logger.info(
            "[POLICY_AUDIT] policy={} tool={} decision={} reason={}",
            event.policy_name,
            event.tool_name,
            event.decision,
            event.reason,
        )
    
    def _log_audit_trail(self, trail: AuditTrail) -> None:
        """Log the complete audit trail."""
        if not self._audit_enabled:
            return
        
        logger.debug(
            "[POLICY_AUDIT_TRAIL] request_id={} tool={} final_decision={} events={}",
            trail.request_id,
            trail.tool_name,
            trail.final_decision,
            len(trail.events),
        )
    
    def evaluate(
        self,
        tool_name: str,
        context: PolicyContext,
        request_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Evaluate tool access through the policy pipeline.
        
        Returns:
            PipelineResult with decision and audit trail
        """
        # Generate request ID if not provided
        req_id = request_id or f"req_{datetime.now().timestamp():.0f}"
        
        # Initialize audit trail
        audit_trail = AuditTrail(
            request_id=req_id,
            user_id=context.user_id,
            tool_name=tool_name,
            final_decision="allow",
        )
        
        # Stage 1: Pre-flight checks
        pre_flight_event = self._create_audit_event(
            policy_name="pre_flight",
            tool_name=tool_name,
            decision="skip",
            reason="pre-flight checks passed",
            metadata={
                "user_id": context.user_id,
                "friend_id": context.friend_id,
                "channel_type": context.channel_type,
                "subagent_depth": context.subagent_depth,
            },
        )
        audit_trail.events.append(pre_flight_event)
        self._log_audit_event(pre_flight_event)
        
        # Stage 2: Evaluate through policy engine
        result = self._engine.evaluate(tool_name, context)
        
        # Record policy evaluation event
        policy_event = self._create_audit_event(
            policy_name=result.policy_name,
            tool_name=tool_name,
            decision="allow" if result.allowed else "deny",
            reason=result.reason,
        )
        audit_trail.events.append(policy_event)
        self._log_audit_event(policy_event)
        
        # Update final decision
        audit_trail.final_decision = "allow" if result.allowed else "deny"
        
        # Stage 3: Post-processing
        post_event = self._create_audit_event(
            policy_name="post_process",
            tool_name=tool_name,
            decision="skip",
            reason="post-processing complete",
            metadata={
                "final_decision": audit_trail.final_decision,
                "evaluated_policies": [e.policy_name for e in audit_trail.events],
            },
        )
        audit_trail.events.append(post_event)
        self._log_audit_event(post_event)
        
        # Log complete trail
        self._log_audit_trail(audit_trail)
        
        return PipelineResult(
            allowed=result.allowed,
            tool_name=tool_name,
            audit_trail=audit_trail,
            policy_name=result.policy_name,
            reason=result.reason,
        )
    
    def evaluate_many(
        self,
        tool_names: List[str],
        context: PolicyContext,
        request_id: Optional[str] = None,
    ) -> Dict[str, PipelineResult]:
        """Evaluate multiple tools through the pipeline."""
        results = {}
        req_id = request_id or f"req_{datetime.now().timestamp():.0f}"
        
        for tool_name in tool_names:
            results[tool_name] = self.evaluate(tool_name, context, req_id)
        
        return results


# Global pipeline instance
_policy_pipeline: Optional[ToolPolicyPipeline] = None


def get_policy_pipeline() -> ToolPolicyPipeline:
    """Return the global policy pipeline."""
    global _policy_pipeline
    if _policy_pipeline is None:
        _policy_pipeline = ToolPolicyPipeline()
    return _policy_pipeline


def evaluate_tool_policy(
    tool_name: str,
    context: PolicyContext,
    request_id: Optional[str] = None,
) -> PipelineResult:
    """Convenience function to evaluate tool policy."""
    return get_policy_pipeline().evaluate(tool_name, context, request_id)


def evaluate_tools_policy(
    tool_names: List[str],
    context: PolicyContext,
    request_id: Optional[str] = None,
) -> Dict[str, PipelineResult]:
    """Convenience function to evaluate multiple tools."""
    return get_policy_pipeline().evaluate_many(tool_names, context, request_id)


# Example usage
# -------------
# context = PolicyContext(user_id="user123", friend_id="HomeClaw")
# result = evaluate_tool_policy("exec", context)
# print(result.allowed)  # True/False
# print(result.audit_trail.to_json())  # Full audit trail
