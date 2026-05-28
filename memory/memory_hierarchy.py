"""
OpenClaw-inspired Memory Hierarchy System

Implements:
1. Memory Types: Episodic, Semantic, Working, Procedural
2. Hierarchical Storage with tiered access
3. Recency-based scoring and eviction policies
4. Context-aware memory retrieval
5. Memory consolidation and summarization
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from memory.base import MemoryBase


class MemoryType(str, Enum):
    """
    Memory types inspired by OpenClaw's hierarchical memory system.
    
    - WORKING: Short-term context (current conversation, expires quickly)
    - EPISODIC: Event-based memories (specific experiences, timestamped)
    - SEMANTIC: General knowledge (facts, concepts, relationships)
    - PROCEDURAL: How-to knowledge (skills, workflows, patterns)
    """
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryTier(int, Enum):
    """
    Memory tier for storage optimization.
    Higher tiers have faster access but more limited capacity.
    """
    TIER_0 = 0  # Fastest, smallest (working memory)
    TIER_1 = 1  # Fast, medium (recent episodic)
    TIER_2 = 2  # Standard, large (semantic/procedural)
    TIER_3 = 3  # Archive, cold storage (old memories)


class MemoryEntry:
    """
    Enhanced memory entry with type, tier, and metadata.
    """
    
    def __init__(
        self,
        memory_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        tier: MemoryTier = MemoryTier.TIER_1,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        accessed_at: Optional[datetime] = None,
        access_count: int = 0,
        score: float = 0.0,
    ):
        self.memory_id = memory_id
        self.content = content
        self.memory_type = memory_type
        self.tier = tier
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.accessed_at = accessed_at
        self.access_count = access_count
        self.score = score
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "tier": self.tier.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "access_count": self.access_count,
            "score": self.score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            memory_id=data["memory_id"],
            content=data["content"],
            memory_type=MemoryType(data.get("memory_type", "episodic")),
            tier=MemoryTier(data.get("tier", 1)),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            accessed_at=datetime.fromisoformat(data["accessed_at"]) if data.get("accessed_at") else None,
            access_count=data.get("access_count", 0),
            score=data.get("score", 0.0),
        )


class MemoryScorer(ABC):
    """
    Base class for memory scoring strategies.
    """
    
    @abstractmethod
    def score(
        self,
        entry: MemoryEntry,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Calculate a relevance score for a memory entry."""
        pass


class RecencyScorer(MemoryScorer):
    """
    Scores memories based on recency with exponential decay.
    """
    
    def __init__(self, half_life_hours: float = 24.0):
        self.half_life_hours = half_life_hours
    
    def score(
        self,
        entry: MemoryEntry,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Calculate recency score (1.0 = now, 0.0 = very old)."""
        now = datetime.now()
        age_hours = (now - entry.created_at).total_seconds() / 3600
        decay_factor = 0.5 ** (age_hours / self.half_life_hours)
        return decay_factor


class FrequencyScorer(MemoryScorer):
    """
    Scores memories based on access frequency.
    """
    
    def __init__(self, max_weight: float = 0.5):
        self.max_weight = max_weight
    
    def score(
        self,
        entry: MemoryEntry,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Calculate frequency score based on access count."""
        if entry.access_count == 0:
            return 0.1
        normalized = min(entry.access_count / 100, 1.0)
        return self.max_weight * normalized


class TypeScorer(MemoryScorer):
    """
    Scores memories based on type and context match.
    """
    
    TYPE_WEIGHTS: Dict[MemoryType, float] = {
        MemoryType.WORKING: 1.0,
        MemoryType.EPISODIC: 0.8,
        MemoryType.SEMANTIC: 0.6,
        MemoryType.PROCEDURAL: 0.7,
    }
    
    def score(
        self,
        entry: MemoryEntry,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Score based on memory type."""
        context_type = context.get("memory_type") if context else None
        
        if context_type and entry.memory_type == context_type:
            return self.TYPE_WEIGHTS.get(entry.memory_type, 0.5) * 1.5
        
        return self.TYPE_WEIGHTS.get(entry.memory_type, 0.5)


class CompositeScorer(MemoryScorer):
    """
    Combines multiple scorers with weighted averaging.
    """
    
    def __init__(
        self,
        scorers: Optional[List[Tuple[MemoryScorer, float]]] = None,
    ):
        self.scorers = scorers or [
            (RecencyScorer(half_life_hours=48), 0.4),
            (FrequencyScorer(max_weight=0.5), 0.3),
            (TypeScorer(), 0.3),
        ]
    
    def score(
        self,
        entry: MemoryEntry,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Combine scores from all scorers."""
        total_weight = sum(weight for _, weight in self.scorers)
        if total_weight == 0:
            return 0.0
        
        total_score = 0.0
        for scorer, weight in self.scorers:
            try:
                total_score += scorer.score(entry, query, context) * weight
            except Exception as e:
                logger.debug(f"Scorer {scorer.__class__.__name__} failed: {e}")
        
        return total_score / total_weight


class MemoryEvictionPolicy(ABC):
    """
    Base class for memory eviction policies.
    """
    
    @abstractmethod
    def should_evict(
        self,
        entry: MemoryEntry,
        current_size: int,
        max_size: int,
    ) -> bool:
        """Determine if a memory should be evicted."""
        pass


class LRUEvictionPolicy(MemoryEvictionPolicy):
    """
    Evicts least recently used memories.
    """
    
    def __init__(self, threshold_hours: float = 72.0):
        self.threshold_hours = threshold_hours
    
    def should_evict(
        self,
        entry: MemoryEntry,
        current_size: int,
        max_size: int,
    ) -> bool:
        """Evict if not accessed in a long time."""
        if current_size < max_size:
            return False
        
        if entry.accessed_at is None:
            return True
        
        age_hours = (datetime.now() - entry.accessed_at).total_seconds() / 3600
        return age_hours > self.threshold_hours


class ScoreBasedEvictionPolicy(MemoryEvictionPolicy):
    """
    Evicts memories with lowest composite score.
    """
    
    def __init__(self, threshold_score: float = 0.2):
        self.threshold_score = threshold_score
    
    def should_evict(
        self,
        entry: MemoryEntry,
        current_size: int,
        max_size: int,
    ) -> bool:
        """Evict if score is below threshold and at capacity."""
        if current_size < max_size:
            return False
        
        return entry.score < self.threshold_score


class HierarchicalMemory(MemoryBase):
    """
    OpenClaw-inspired hierarchical memory system with:
    - Multiple memory types (working, episodic, semantic, procedural)
    - Tiered storage with automatic promotion/demotion
    - Smart scoring and retrieval
    - Automatic consolidation and summarization
    """
    
    def __init__(
        self,
        backend: MemoryBase,
        scorer: Optional[MemoryScorer] = None,
        eviction_policy: Optional[MemoryEvictionPolicy] = None,
        max_entries: int = 10000,
        working_memory_ttl_hours: float = 4.0,
    ):
        self.backend = backend
        self.scorer = scorer or CompositeScorer()
        self.eviction_policy = eviction_policy or LRUEvictionPolicy()
        self.max_entries = max_entries
        self.working_memory_ttl_hours = working_memory_ttl_hours
        
        # In-memory cache for working memory
        self._working_cache: Dict[str, MemoryEntry] = {}
        
        # Tier size limits
        self._tier_limits = {
            MemoryTier.TIER_0: 100,    # Working memory
            MemoryTier.TIER_1: 1000,   # Recent episodic
            MemoryTier.TIER_2: 5000,   # Main storage
            MemoryTier.TIER_3: 10000,  # Archive
        }
    
    async def _load_working_memory(self, user_id: Optional[str] = None) -> None:
        """Load working memory from backend."""
        filters = {"memory_type": MemoryType.WORKING.value}
        if user_id:
            filters["user_id"] = user_id
        
        results = await self.backend.search("", filters=filters, limit=self._tier_limits[MemoryTier.TIER_0])
        for item in results:
            try:
                entry = MemoryEntry.from_dict(item)
                self._working_cache[entry.memory_id] = entry
            except Exception as e:
                logger.debug(f"Failed to load working memory entry: {e}")
    
    async def _sync_working_memory(self) -> None:
        """Sync working memory cache to backend."""
        for entry in self._working_cache.values():
            try:
                # Update or create in backend
                existing = await self._get_from_backend(entry.memory_id)
                if existing:
                    await self._update_in_backend(entry)
                else:
                    await self._add_to_backend(entry)
            except Exception as e:
                logger.debug(f"Failed to sync working memory: {e}")
    
    async def _add_to_backend(self, entry: MemoryEntry) -> None:
        """Add memory entry to backend."""
        metadata = {
            "memory_type": entry.memory_type.value,
            "tier": entry.tier.value,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "accessed_at": entry.accessed_at.isoformat() if entry.accessed_at else None,
            "access_count": entry.access_count,
            "score": entry.score,
            **(entry.metadata or {}),
        }
        await self.backend.add(
            data=entry.content,
            metadata=metadata,
        )
    
    async def _update_in_backend(self, entry: MemoryEntry) -> None:
        """Update memory entry in backend."""
        # This is a simplified version - actual implementation would need update support
        metadata = {
            "memory_type": entry.memory_type.value,
            "tier": entry.tier.value,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "accessed_at": entry.accessed_at.isoformat() if entry.accessed_at else None,
            "access_count": entry.access_count,
            "score": entry.score,
            **(entry.metadata or {}),
        }
        await self.backend.add(
            data=entry.content,
            metadata=metadata,
        )
    
    async def _get_from_backend(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve memory entry from backend."""
        result = self.backend.get(memory_id)
        if result:
            return MemoryEntry.from_dict(result)
        return None
    
    async def _get_all_from_backend(self, filters: Optional[Dict] = None) -> List[MemoryEntry]:
        """Get all entries from backend matching filters."""
        results = self.backend.get_all(filters=filters)
        entries = []
        for item in results:
            try:
                entries.append(MemoryEntry.from_dict(item))
            except Exception as e:
                logger.debug(f"Failed to parse memory entry: {e}")
        return entries
    
    async def _evict_candidates(self) -> List[str]:
        """Identify memories to evict based on policy."""
        all_entries = await self._get_all_from_backend()
        all_entries.sort(key=lambda e: e.score)
        
        evict_ids = []
        current_size = len(all_entries)
        
        for entry in all_entries:
            if current_size <= self.max_entries:
                break
            if self.eviction_policy.should_evict(entry, current_size, self.max_entries):
                evict_ids.append(entry.memory_id)
                current_size -= 1
        
        return evict_ids
    
    async def _promote_memory(self, entry: MemoryEntry) -> None:
        """Promote memory to a higher tier if frequently accessed."""
        if entry.tier == MemoryTier.TIER_0:
            return  # Already highest tier
        
        if entry.access_count >= 10:
            entry.tier = MemoryTier(entry.tier.value - 1)
            entry.updated_at = datetime.now()
            await self._update_in_backend(entry)
            logger.debug(f"Promoted memory {entry.memory_id} to tier {entry.tier}")
    
    async def _demote_memory(self, entry: MemoryEntry) -> None:
        """Demote memory to a lower tier if rarely accessed."""
        if entry.tier == MemoryTier.TIER_3:
            return  # Already lowest tier
        
        if entry.access_count == 0 and (datetime.now() - entry.created_at).days > 30:
            entry.tier = MemoryTier(entry.tier.value + 1)
            entry.updated_at = datetime.now()
            await self._update_in_backend(entry)
            logger.debug(f"Demoted memory {entry.memory_id} to tier {entry.tier}")
    
    async def add(
        self,
        data: str,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        filters: Optional[Dict] = None,
        prompt: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> List[Dict[str, Any]]:
        """
        Add a new memory with type classification.
        
        Args:
            memory_type: Explicit memory type, or auto-detect if None
        """
        # Auto-detect memory type based on content
        detected_type = memory_type or self._detect_memory_type(data)
        
        # Determine tier based on type
        tier = self._get_tier_for_type(detected_type)
        
        # Create memory entry
        memory_id = hashlib.md5((data + str(datetime.now())).encode()).hexdigest()
        entry = MemoryEntry(
            memory_id=memory_id,
            content=data,
            memory_type=detected_type,
            tier=tier,
            metadata={
                **(metadata or {}),
                "user_name": user_name,
                "user_id": user_id,
                "agent_id": agent_id,
                "run_id": run_id,
            },
        )
        
        # Add to working cache if working memory
        if detected_type == MemoryType.WORKING:
            self._working_cache[memory_id] = entry
        
        # Add to backend
        await self._add_to_backend(entry)
        
        # Check eviction
        await self._check_eviction()
        
        return [{
            "id": memory_id,
            "event": "add",
            "data": data,
            "memory_type": detected_type.value,
        }]
    
    def _detect_memory_type(self, content: str) -> MemoryType:
        """
        Auto-detect memory type based on content characteristics.
        
        Rules:
        - Short, recent context → WORKING
        - Narrative with timestamps → EPISODIC
        - Factual statements → SEMANTIC
        - Step-by-step instructions → PROCEDURAL
        """
        content_lower = content.lower()
        
        # Check for procedural patterns
        procedural_patterns = [
            "step", "how to", "first", "then", "next", "finally",
            "should", "must", "need to", "follow", "execute",
        ]
        if any(pattern in content_lower for pattern in procedural_patterns):
            return MemoryType.PROCEDURAL
        
        # Check for semantic patterns (facts, definitions)
        semantic_patterns = [
            "is a", "means", "definition", "fact", "known as",
            "according to", "states that", "the concept of",
        ]
        if any(pattern in content_lower for pattern in semantic_patterns):
            return MemoryType.SEMANTIC
        
        # Check for episodic patterns (events, experiences)
        episodic_patterns = [
            "today", "yesterday", "last week", "I remember",
            "we did", "happened", "during", "when",
        ]
        if any(pattern in content_lower for pattern in episodic_patterns):
            return MemoryType.EPISODIC
        
        # Default to episodic
        return MemoryType.EPISODIC
    
    def _get_tier_for_type(self, memory_type: MemoryType) -> MemoryTier:
        """Determine storage tier based on memory type."""
        tier_map = {
            MemoryType.WORKING: MemoryTier.TIER_0,
            MemoryType.EPISODIC: MemoryTier.TIER_1,
            MemoryType.SEMANTIC: MemoryTier.TIER_2,
            MemoryType.PROCEDURAL: MemoryTier.TIER_2,
        }
        return tier_map.get(memory_type, MemoryTier.TIER_1)
    
    async def search(
        self,
        query: str,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
        filters: Optional[Dict] = None,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories with context-aware scoring.
        
        Args:
            memory_types: Filter by specific memory types
        """
        # Build filters
        search_filters = filters or {}
        if user_id:
            search_filters["user_id"] = user_id
        if user_name:
            search_filters["user_name"] = user_name
        if agent_id:
            search_filters["agent_id"] = agent_id
        if run_id:
            search_filters["run_id"] = run_id
        
        # Add type filter if specified
        if memory_types:
            search_filters["memory_type"] = [t.value for t in memory_types]
        
        # Search backend
        results = await self.backend.search(query, filters=search_filters, limit=limit * 2)
        
        # Convert to MemoryEntry objects
        entries = []
        for item in results:
            try:
                # Handle both dict and object results
                if isinstance(item, dict):
                    entry = MemoryEntry.from_dict(item)
                else:
                    # Legacy format support
                    entry = MemoryEntry(
                        memory_id=getattr(item, "id", str(hash(item))),
                        content=getattr(item, "memory", "") or getattr(item, "data", "") or str(item),
                        metadata=getattr(item, "metadata", {}),
                        created_at=datetime.now(),
                    )
                entries.append(entry)
            except Exception as e:
                logger.debug(f"Failed to parse search result: {e}")
        
        # Add working memory entries
        for entry in self._working_cache.values():
            if user_id and entry.metadata.get("user_id") != user_id:
                continue
            entries.append(entry)
        
        # Score and sort entries
        context = {"memory_type": memory_types[0] if memory_types else None}
        for entry in entries:
            entry.score = self.scorer.score(entry, query, context)
        
        # Sort by score (descending)
        entries.sort(key=lambda e: e.score, reverse=True)
        
        # Update access tracking
        now = datetime.now()
        for entry in entries[:limit]:
            entry.accessed_at = now
            entry.access_count += 1
        
        # Sync working memory
        await self._sync_working_memory()
        
        # Convert to output format
        output = []
        for entry in entries[:limit]:
            item = entry.to_dict()
            item["user_name"] = entry.metadata.get("user_name")
            item["user_id"] = entry.metadata.get("user_id")
            item["agent_id"] = entry.metadata.get("agent_id")
            item["run_id"] = entry.metadata.get("run_id")
            output.append(item)
        
        return output
    
    async def _check_eviction(self) -> None:
        """Check if any memories need to be evicted."""
        evict_ids = await self._evict_candidates()
        for memory_id in evict_ids:
            await self.delete(memory_id)
            if memory_id in self._working_cache:
                del self._working_cache[memory_id]
            logger.debug(f"Evicted memory {memory_id}")
    
    async def consolidate_memory(self, user_id: Optional[str] = None) -> None:
        """
        Consolidate old episodic memories into semantic knowledge.
        This is a simplified version - would typically use LLM summarization.
        """
        filters = {"memory_type": MemoryType.EPISODIC.value}
        if user_id:
            filters["user_id"] = user_id
        
        entries = await self._get_all_from_backend(filters)
        
        # Group by week
        week_groups = {}
        for entry in entries:
            week_key = entry.created_at.isocalendar()[:2]  # (year, week)
            if week_key not in week_groups:
                week_groups[week_key] = []
            week_groups[week_key].append(entry)
        
        # Create summaries for weeks with multiple entries
        for week_key, week_entries in week_groups.items():
            if len(week_entries) < 3:
                continue
            
            # Create consolidated summary
            contents = [e.content for e in week_entries]
            summary = f"Week {week_key[1]} {week_key[0]} summary:\n" + "\n".join(contents)
            
            # Add as semantic memory
            await self.add(
                data=summary,
                memory_type=MemoryType.SEMANTIC,
                metadata={"consolidated_from": [e.memory_id for e in week_entries]},
            )
            
            # Mark original entries for deletion
            for entry in week_entries:
                entry.tier = MemoryTier.TIER_3  # Move to archive
        
        logger.debug("Memory consolidation completed")
    
    async def cleanup_working_memory(self) -> None:
        """Clean up expired working memory entries."""
        now = datetime.now()
        expired_ids = []
        
        for memory_id, entry in self._working_cache.items():
            age_hours = (now - entry.created_at).total_seconds() / 3600
            if age_hours > self.working_memory_ttl_hours:
                expired_ids.append(memory_id)
        
        for memory_id in expired_ids:
            del self._working_cache[memory_id]
            await self.delete(memory_id)
        
        if expired_ids:
            logger.debug(f"Cleaned up {len(expired_ids)} expired working memory entries")
    
    # --- Delegated methods ---
    
    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a memory by ID."""
        # Check working cache first
        if memory_id in self._working_cache:
            return self._working_cache[memory_id].to_dict()
        
        # Fall back to backend
        result = self.backend.get(memory_id)
        if result:
            return MemoryEntry.from_dict(result).to_dict()
        return None
    
    def get_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List all memories."""
        entries = self.backend.get_all(
            user_name=user_name,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            limit=limit,
        )
        return [MemoryEntry.from_dict(e).to_dict() for e in entries]
    
    def update(self, memory_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a memory."""
        # Update in working cache
        if memory_id in self._working_cache:
            entry = self._working_cache[memory_id]
            entry.content = data.get("content", entry.content)
            entry.metadata.update(data.get("metadata", {}))
            entry.updated_at = datetime.now()
        
        # Update in backend
        return self.backend.update(memory_id, data)
    
    def delete(self, memory_id: str) -> None:
        """Delete a memory."""
        # Remove from working cache
        if memory_id in self._working_cache:
            del self._working_cache[memory_id]
        
        # Delete from backend
        self.backend.delete(memory_id)
    
    def delete_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete all memories."""
        # Clear working cache
        self._working_cache.clear()
        
        # Delete from backend
        return self.backend.delete_all(
            user_name=user_name,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
        )
    
    def history(self, memory_id: str) -> List[Any]:
        """Get history of changes for a memory."""
        return self.backend.history(memory_id)
    
    def supports_summarization(self) -> bool:
        """Whether this backend supports summarization."""
        return self.backend.supports_summarization()
    
    def reset(self) -> None:
        """Reset all memory."""
        self._working_cache.clear()
        self.backend.reset()
    
    def chat(self, query: str) -> Any:
        """Chat interface (not implemented)."""
        raise NotImplementedError("Chat function not implemented.")


# Convenience functions
def create_hierarchical_memory(
    backend: MemoryBase,
    **kwargs,
) -> HierarchicalMemory:
    """Create a hierarchical memory instance with default settings."""
    return HierarchicalMemory(backend, **kwargs)


def get_memory_type_names() -> List[str]:
    """Get list of memory type names."""
    return [t.value for t in MemoryType]


def get_memory_tier_names() -> List[str]:
    """Get list of memory tier names."""
    return [f"tier_{t.value}" for t in MemoryTier]