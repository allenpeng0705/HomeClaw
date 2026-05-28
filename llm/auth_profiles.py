"""
Model auth profiles — Phase 6: Per-agent API key rotation with fallback strategies.

Inspired by OpenClaw's agents/model-auth.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RotationStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    FALLBACK = "fallback"
    RANDOM = "random"


@dataclass
class AuthProfile:
    provider: str
    api_key: str
    weight: int = 1
    label: str = ""


@dataclass
class AgentAuthConfig:
    agent_id: str
    profiles: List[AuthProfile] = field(default_factory=list)
    strategy: RotationStrategy = RotationStrategy.ROUND_ROBIN
    _round_robin_index: int = field(default=0, repr=False)


def load_auth_profiles(config: Optional[Dict[str, Any]]) -> Dict[str, AgentAuthConfig]:
    """
    Load per-agent auth profiles from config.

    Config format:
        auth_profiles:
          default:
            strategy: round_robin
            profiles:
              - {provider: deepseek, api_key: "sk-xxx", weight: 1, label: primary}
              - {provider: deepseek, api_key: "sk-yyy", weight: 1, label: backup}
          clawcode:
            strategy: fallback
            profiles:
              - {provider: openai, api_key: "sk-aaa"}
              - {provider: anthropic, api_key: "sk-bbb"}
    """
    agents: Dict[str, AgentAuthConfig] = {}
    if not isinstance(config, dict):
        return agents

    for agent_id, agent_cfg in config.items():
        if not isinstance(agent_cfg, dict):
            continue
        try:
            strategy = RotationStrategy(agent_cfg.get("strategy", "round_robin"))
        except ValueError:
            strategy = RotationStrategy.ROUND_ROBIN

        profiles: List[AuthProfile] = []
        for p in agent_cfg.get("profiles") or []:
            if not isinstance(p, dict):
                continue
            profiles.append(AuthProfile(
                provider=p.get("provider", ""),
                api_key=p.get("api_key", ""),
                weight=p.get("weight", 1),
                label=p.get("label", ""),
            ))

        if profiles:
            agents[agent_id] = AgentAuthConfig(
                agent_id=agent_id,
                profiles=profiles,
                strategy=strategy,
            )

    return agents


def rotate_key(config: AgentAuthConfig) -> Optional[AuthProfile]:
    """
    Rotate to the next API key according to the strategy.

    Returns the selected AuthProfile, or None if no profiles are configured.
    """
    if not config.profiles:
        return None

    if config.strategy == RotationStrategy.ROUND_ROBIN:
        idx = config._round_robin_index % len(config.profiles)
        config._round_robin_index += 1
        return config.profiles[idx]

    if config.strategy == RotationStrategy.WEIGHTED:
        import random
        total = sum(p.weight for p in config.profiles)
        r = random.uniform(0, total)
        cumulative = 0
        for p in config.profiles:
            cumulative += p.weight
            if r <= cumulative:
                return p
        return config.profiles[-1]

    if config.strategy == RotationStrategy.FALLBACK:
        # Always return the first profile (primary)
        return config.profiles[0]

    if config.strategy == RotationStrategy.RANDOM:
        import random
        return random.choice(config.profiles)

    return config.profiles[0]


def resolve_auth_for_agent(
    agent_id: str,
    agents: Dict[str, AgentAuthConfig],
) -> Optional[AuthProfile]:
    """Resolve the active auth profile for an agent."""
    cfg = agents.get(agent_id) or agents.get("default")
    if cfg is None:
        return None
    return rotate_key(cfg)
