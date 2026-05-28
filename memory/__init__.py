"""
Memory backends: Cognee adapter, Chroma, knowledge base, etc.

Apply Instructor/litellm patch as soon as this package is imported so cognify
works with local LLMs (before any code imports cognee or instructor).

OpenClaw-inspired enhancements:
- Hierarchical memory system with multiple memory types
- Smart retrieval with query expansion and context awareness
"""
from __future__ import annotations

try:
    from memory.instructor_patch import apply_instructor_patch_for_local_llm
    apply_instructor_patch_for_local_llm()
except Exception:
    pass

# OpenClaw-inspired hierarchical memory
from memory.memory_hierarchy import (
    HierarchicalMemory,
    MemoryType,
    MemoryTier,
    MemoryEntry,
    CompositeScorer,
    RecencyScorer,
    FrequencyScorer,
    TypeScorer,
    LRUEvictionPolicy,
    ScoreBasedEvictionPolicy,
    create_hierarchical_memory,
    get_memory_type_names,
    get_memory_tier_names,
)

# OpenClaw-inspired smart retrieval
from memory.smart_retrieval import (
    SmartMemoryRetrieval,
    QueryExpander,
    ContextAnalyzer,
    MemoryFuser,
    create_smart_retrieval,
    smart_search,
)