"""Tests for OpenClaw-inspired memory hierarchy and smart retrieval."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

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
)
from memory.smart_retrieval import (
    SmartMemoryRetrieval,
    QueryExpander,
    ContextAnalyzer,
    MemoryFuser,
)


class TestMemoryTypes:
    """Test memory type enumeration."""
    
    def test_memory_types(self):
        """Test memory type values."""
        assert MemoryType.WORKING.value == "working"
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.PROCEDURAL.value == "procedural"
    
    def test_memory_tiers(self):
        """Test memory tier values."""
        assert MemoryTier.TIER_0.value == 0
        assert MemoryTier.TIER_1.value == 1
        assert MemoryTier.TIER_2.value == 2
        assert MemoryTier.TIER_3.value == 3


class TestMemoryEntry:
    """Test memory entry class."""
    
    def test_memory_entry_creation(self):
        """Test creating a memory entry."""
        entry = MemoryEntry(
            memory_id="test-id",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
            tier=MemoryTier.TIER_1,
        )
        
        assert entry.memory_id == "test-id"
        assert entry.content == "Test content"
        assert entry.memory_type == MemoryType.EPISODIC
        assert entry.tier == MemoryTier.TIER_1
    
    def test_memory_entry_to_dict(self):
        """Test converting entry to dictionary."""
        entry = MemoryEntry(
            memory_id="test-id",
            content="Test content",
            memory_type=MemoryType.EPISODIC,
        )
        
        data = entry.to_dict()
        assert data["memory_id"] == "test-id"
        assert data["content"] == "Test content"
        assert data["memory_type"] == "episodic"
    
    def test_memory_entry_from_dict(self):
        """Test creating entry from dictionary."""
        data = {
            "memory_id": "test-id",
            "content": "Test content",
            "memory_type": "episodic",
            "tier": 1,
            "metadata": {"key": "value"},
        }
        
        entry = MemoryEntry.from_dict(data)
        assert entry.memory_id == "test-id"
        assert entry.content == "Test content"
        assert entry.memory_type == MemoryType.EPISODIC
        assert entry.tier == MemoryTier.TIER_1


class TestMemoryScorers:
    """Test memory scoring strategies."""
    
    def test_recency_scorer(self):
        """Test recency-based scoring."""
        scorer = RecencyScorer(half_life_hours=1.0)
        entry = MemoryEntry(
            memory_id="test",
            content="Test",
        )
        
        score = scorer.score(entry, "query")
        assert 0.0 <= score <= 1.0
    
    def test_frequency_scorer(self):
        """Test frequency-based scoring."""
        scorer = FrequencyScorer(max_weight=0.5)
        
        # Entry with no accesses
        entry1 = MemoryEntry(memory_id="test1", content="Test", access_count=0)
        score1 = scorer.score(entry1, "query")
        assert score1 == 0.1
        
        # Entry with many accesses
        entry2 = MemoryEntry(memory_id="test2", content="Test", access_count=50)
        score2 = scorer.score(entry2, "query")
        assert score2 > score1
    
    def test_type_scorer(self):
        """Test type-based scoring."""
        scorer = TypeScorer()
        
        entry = MemoryEntry(
            memory_id="test",
            content="Test",
            memory_type=MemoryType.WORKING,
        )
        
        score = scorer.score(entry, "query")
        assert score > 0.0
    
    def test_composite_scorer(self):
        """Test composite scoring."""
        scorer = CompositeScorer()
        entry = MemoryEntry(
            memory_id="test",
            content="Test",
            memory_type=MemoryType.EPISODIC,
            access_count=5,
        )
        
        score = scorer.score(entry, "query")
        assert 0.0 <= score <= 1.0


class TestEvictionPolicies:
    """Test memory eviction policies."""
    
    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        policy = LRUEvictionPolicy(threshold_hours=1.0)
        
        entry = MemoryEntry(
            memory_id="test",
            content="Test",
        )
        
        # Not at capacity - should not evict
        result = policy.should_evict(entry, current_size=50, max_size=100)
        assert result is False
    
    def test_score_based_eviction(self):
        """Test score-based eviction policy."""
        policy = ScoreBasedEvictionPolicy(threshold_score=0.2)
        
        # Low score entry
        entry_low = MemoryEntry(memory_id="low", content="Test", score=0.1)
        result_low = policy.should_evict(entry_low, current_size=100, max_size=100)
        assert result_low is True
        
        # High score entry
        entry_high = MemoryEntry(memory_id="high", content="Test", score=0.5)
        result_high = policy.should_evict(entry_high, current_size=100, max_size=100)
        assert result_high is False


class TestHierarchicalMemory:
    """Test hierarchical memory system."""
    
    @pytest.fixture
    def mock_backend(self):
        """Create a mock memory backend."""
        backend = MagicMock()
        backend.add = AsyncMock(return_value=[{"id": "test-id", "event": "add"}])
        backend.search = AsyncMock(return_value=[])
        backend.get = MagicMock(return_value=None)
        backend.get_all = MagicMock(return_value=[])
        backend.update = MagicMock(return_value={"message": "updated"})
        backend.delete = MagicMock()
        backend.delete_all = MagicMock(return_value={"message": "deleted"})
        backend.history = MagicMock(return_value=[])
        backend.supports_summarization = MagicMock(return_value=True)
        backend.reset = MagicMock()
        backend.chat = MagicMock(side_effect=NotImplementedError)
        return backend
    
    @pytest.mark.asyncio
    async def test_add_memory(self, mock_backend):
        """Test adding memory with auto-type detection."""
        memory = HierarchicalMemory(backend=mock_backend)
        
        result = await memory.add(
            data="I went to the store today and bought milk",
            user_id="user123",
        )
        
        assert len(result) == 1
        assert result[0]["memory_type"] == MemoryType.EPISODIC.value
    
    @pytest.mark.asyncio
    async def test_add_working_memory(self, mock_backend):
        """Test adding working memory."""
        memory = HierarchicalMemory(backend=mock_backend)
        
        result = await memory.add(
            data="Remember: user likes coffee",
            user_id="user123",
            memory_type=MemoryType.WORKING,
        )
        
        assert result[0]["memory_type"] == MemoryType.WORKING.value
        assert len(memory._working_cache) == 1
        entry = next(iter(memory._working_cache.values()))
        assert "Remember" in entry.content
    
    @pytest.mark.asyncio
    async def test_detect_memory_type(self, mock_backend):
        """Test automatic memory type detection."""
        memory = HierarchicalMemory(backend=mock_backend)
        
        # Test procedural detection
        procedural_content = "Step 1: Open the file. Step 2: Edit the content."
        mem_type = memory._detect_memory_type(procedural_content)
        assert mem_type == MemoryType.PROCEDURAL
        
        # Test semantic detection
        semantic_content = "Python is a programming language known for its readability."
        mem_type = memory._detect_memory_type(semantic_content)
        assert mem_type == MemoryType.SEMANTIC
        
        # Test episodic detection
        episodic_content = "Yesterday I went to the park with my friends."
        mem_type = memory._detect_memory_type(episodic_content)
        assert mem_type == MemoryType.EPISODIC
    
    @pytest.mark.asyncio
    async def test_search_memory(self, mock_backend):
        """Test searching memory."""
        mock_backend.search = AsyncMock(return_value=[
            {
                "memory_id": "test1",
                "content": "Test content",
                "memory_type": "episodic",
                "tier": 1,
                "metadata": {"user_id": "user123"},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "access_count": 0,
                "score": 0.5,
            }
        ])
        
        memory = HierarchicalMemory(backend=mock_backend)
        
        results = await memory.search(
            query="test",
            user_id="user123",
        )
        
        assert len(results) == 1
        assert results[0]["content"] == "Test content"


class TestSmartRetrieval:
    """Test smart memory retrieval."""
    
    def test_query_expander(self):
        """Test query expansion."""
        expander = QueryExpander()
        
        expansions = expander.expand("search for file")
        
        assert "search for file" in expansions
        assert len(expansions) > 1
    
    def test_context_analyzer(self):
        """Test context analyzer."""
        analyzer = ContextAnalyzer()
        
        analyzer.add_message("user", "I need help with Python code")
        analyzer.add_message("assistant", "Sure! What do you need help with?")
        
        terms = analyzer.extract_key_terms()
        assert len(terms) > 0
        
        # Test topic change detection
        is_change = analyzer.is_topic_change("What's the weather today?")
        assert is_change is True
        
        is_same = analyzer.is_topic_change("How do I write a Python function?")
        assert is_same is False
    
    def test_memory_fuser(self):
        """Test memory fuser."""
        fuser = MemoryFuser()
        
        sources = [
            ("source1", [
                {"content": "A", "score": 0.9},
                {"content": "B", "score": 0.7},
            ]),
            ("source2", [
                {"content": "A", "score": 0.8},
                {"content": "C", "score": 0.6},
            ]),
        ]
        
        fused = fuser.fuse(sources)
        
        assert len(fused) == 3  # A, B, C (A deduplicated)
        assert fused[0]["content"] == "A"  # Highest combined score
    
    @pytest.mark.asyncio
    async def test_smart_retrieval(self):
        """Test smart retrieval flow."""
        # Create mock hierarchical memory
        mock_backend = MagicMock()
        mock_backend.search = AsyncMock(return_value=[
            {
                "memory_id": "test1",
                "content": "Relevant memory",
                "memory_type": "episodic",
                "tier": 1,
                "metadata": {},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "access_count": 0,
                "score": 0.8,
            }
        ])
        
        hierarchical_memory = HierarchicalMemory(backend=mock_backend)
        retrieval = SmartMemoryRetrieval(memory=hierarchical_memory)
        
        results = await retrieval.retrieve(
            query="find relevant info",
            user_id="user123",
        )
        
        assert len(results) > 0
        assert "Relevant memory" in results[0]["content"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])