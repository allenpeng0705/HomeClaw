"""
OpenClaw-inspired Smart Memory Retrieval

Implements:
1. Query expansion for better recall
2. Context-aware retrieval (conversational context)
3. Multi-modal similarity scoring
4. Reranking based on relevance
5. Memory fusion from multiple sources
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from memory.base import MemoryBase
from memory.memory_hierarchy import HierarchicalMemory, MemoryType


class QueryExpander:
    """
    Expands user queries to improve memory retrieval.
    
    Techniques:
    - Synonym expansion
    - Concept expansion
    - Historical context injection
    - Query rewriting
    """
    
    # Common synonyms for memory retrieval
    SYNONYMS: Dict[str, List[str]] = {
        "file": ["document", "text", "file", "pdf", "doc", "document"],
        "search": ["find", "locate", "search", "look for", "retrieve"],
        "code": ["program", "script", "code", "function", "method"],
        "memory": ["remember", "recall", "memory", "knowledge", "fact"],
        "help": ["assist", "help", "guide", "support", "explain"],
        "how": ["how", "steps", "process", "method", "way"],
        "what": ["what", "define", "explain", "describe", "meaning"],
        "when": ["when", "time", "date", "history", "past"],
        "where": ["where", "location", "path", "directory", "folder"],
        "who": ["who", "person", "user", "author", "creator"],
    }
    
    def __init__(self):
        self._expanded_cache: Dict[str, List[str]] = {}
    
    def expand(self, query: str, context: Optional[List[str]] = None) -> List[str]:
        """
        Expand a query into multiple related queries for better recall.
        
        Args:
            query: Original user query
            context: Optional list of context terms from conversation
        
        Returns:
            List of expanded query variations
        """
        if query in self._expanded_cache:
            return self._expanded_cache[query]
        
        expansions = [query]
        
        # Tokenize query
        tokens = self._tokenize(query)
        
        # Generate synonym variations
        for token in tokens:
            if token.lower() in self.SYNONYMS:
                for synonym in self.SYNONYMS[token.lower()]:
                    if synonym != token:
                        expanded = query.replace(token, synonym)
                        expansions.append(expanded)
        
        # Add context variations if context provided
        if context:
            for ctx_term in context[:3]:
                expansions.append(f"{query} {ctx_term}")
                expansions.append(f"{ctx_term} {query}")
        
        # Add wildcard variations
        expansions.append(f"{query}*")
        expansions.append(f"*{query}*")
        
        # Remove duplicates and sort by relevance
        unique_expansions = list(dict.fromkeys(expansions))
        unique_expansions.sort(key=lambda x: self._score_expansion(x, query))
        
        self._expanded_cache[query] = unique_expansions
        return unique_expansions
    
    def _tokenize(self, query: str) -> List[str]:
        """Tokenize query into meaningful terms."""
        # Remove punctuation and split
        cleaned = re.sub(r"[^\w\s]", "", query)
        tokens = [t for t in cleaned.split() if len(t) > 2]
        return tokens
    
    def _score_expansion(self, expansion: str, original: str) -> float:
        """Score expansion by similarity to original query."""
        original_tokens = set(self._tokenize(original.lower()))
        expansion_tokens = set(self._tokenize(expansion.lower()))
        
        if not original_tokens:
            return 0.0
        
        overlap = len(original_tokens & expansion_tokens)
        return overlap / len(original_tokens)


class ContextAnalyzer:
    """
    Analyzes conversation context to improve memory retrieval.
    
    Features:
    - Identifies topic changes
    - Extracts key entities
    - Tracks conversation history
    - Determines context window
    """
    
    def __init__(self, max_context_size: int = 10):
        self.max_context_size = max_context_size
        self.conversation_history: List[Dict[str, str]] = []
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
        })
        
        # Trim to max size
        if len(self.conversation_history) > self.max_context_size:
            self.conversation_history = self.conversation_history[-self.max_context_size:]
    
    def extract_key_terms(self, limit: int = 5) -> List[str]:
        """Extract key terms from conversation context."""
        terms = []
        
        for msg in reversed(self.conversation_history):
            content = msg.get("content", "")
            tokens = self._extract_important_tokens(content)
            terms.extend(tokens)
        
        # Deduplicate and limit
        unique_terms = list(dict.fromkeys(terms))[:limit]
        return unique_terms
    
    def _extract_important_tokens(self, text: str) -> List[str]:
        """Extract important tokens from text."""
        # Remove common stopwords
        stopwords = {"the", "and", "is", "are", "be", "to", "of", "a", "in", "for", "on", "with", "as", "at", "by", "this", "that", "these", "those", "from", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "or", "but", "if", "because", "while", "although", "though", "unless", "until", "since", "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must"}
        
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        tokens = [t for t in cleaned.split() if len(t) > 2 and t not in stopwords]
        
        return tokens
    
    def is_topic_change(self, new_query: str, threshold: float = 0.3) -> bool:
        """Detect if new query represents a topic change."""
        if not self.conversation_history:
            return False
        
        recent_content = " ".join(
            msg.get("content", "") for msg in self.conversation_history[-3:]
        )
        
        new_tokens = set(self._extract_important_tokens(new_query))
        old_tokens = set(self._extract_important_tokens(recent_content))
        
        if not new_tokens or not old_tokens:
            return False
        
        overlap = len(new_tokens & old_tokens)
        similarity = overlap / len(new_tokens)
        
        return similarity < threshold


class MemoryFuser:
    """
    Fuses results from multiple memory sources.
    
    Features:
    - Deduplication
    - Score normalization
    - Cross-source ranking
    - Confidence estimation
    """
    
    def __init__(self, max_results: int = 20):
        self.max_results = max_results
    
    def fuse(
        self,
        sources: List[Tuple[str, List[Dict[str, Any]]]],
        weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fuse results from multiple sources.
        
        Args:
            sources: List of (source_name, results) tuples
            weights: Optional weights for each source
        
        Returns:
            Combined and ranked results
        """
        all_results = []
        
        for source_name, results in sources:
            weight = weights.get(source_name, 1.0) if weights else 1.0
            
            for result in results:
                # Apply source weight to score
                weighted_score = (result.get("score", 0.0) or 0.0) * weight
                
                all_results.append({
                    **result,
                    "source": source_name,
                    "weighted_score": weighted_score,
                    "original_score": result.get("score", 0.0),
                })
        
        # Deduplicate by content
        seen_contents = set()
        unique_results = []
        
        for result in all_results:
            content = result.get("content", "") or result.get("memory", "")
            content_key = content[:200].strip()
            
            if content_key and content_key in seen_contents:
                continue
            
            seen_contents.add(content_key)
            unique_results.append(result)
        
        # Sort by weighted score
        unique_results.sort(key=lambda x: x.get("weighted_score", 0.0), reverse=True)
        
        return unique_results[:self.max_results]


class SmartMemoryRetrieval:
    """
    OpenClaw-inspired smart memory retrieval system.
    
    Combines:
    - Query expansion
    - Context analysis
    - Multi-source fusion
    - Intelligent ranking
    """
    
    def __init__(
        self,
        memory: HierarchicalMemory,
        query_expander: Optional[QueryExpander] = None,
        context_analyzer: Optional[ContextAnalyzer] = None,
        memory_fuser: Optional[MemoryFuser] = None,
    ):
        self.memory = memory
        self.query_expander = query_expander or QueryExpander()
        self.context_analyzer = context_analyzer or ContextAnalyzer()
        self.memory_fuser = memory_fuser or MemoryFuser()
    
    async def retrieve(
        self,
        query: str,
        user_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Smart memory retrieval with query expansion and context awareness.
        
        Args:
            query: User query
            user_id: Optional user ID for filtering
            context: Optional conversation context
            memory_types: Optional memory type filter
            limit: Maximum number of results
        
        Returns:
            Ranked and deduplicated memory results
        """
        # Update context analyzer
        if context:
            for msg in context:
                self.context_analyzer.add_message(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                )
        
        # Expand query
        key_terms = self.context_analyzer.extract_key_terms()
        expanded_queries = self.query_expander.expand(query, key_terms)
        
        logger.debug(f"Original query: {query}")
        logger.debug(f"Expanded queries: {expanded_queries[:5]}")
        
        # Check for topic change
        is_topic_change = self.context_analyzer.is_topic_change(query)
        logger.debug(f"Topic change detected: {is_topic_change}")
        
        # If topic changed, focus on working memory first
        if is_topic_change:
            primary_types = [MemoryType.WORKING]
        else:
            primary_types = memory_types or [MemoryType.EPISODIC, MemoryType.SEMANTIC]
        
        # Collect results from multiple sources
        sources = []
        
        # Search with each expanded query
        for i, expanded_query in enumerate(expanded_queries[:3]):  # Limit to top 3 expansions
            results = await self.memory.search(
                query=expanded_query,
                user_id=user_id,
                memory_types=primary_types,
                limit=limit * 2,
            )
            
            # Tag with query source
            for r in results:
                r["query_source"] = expanded_query
            
            sources.append((f"query_{i}", results))
        
        # Also search with original query across all types
        all_types = memory_types or list(MemoryType)
        original_results = await self.memory.search(
            query=query,
            user_id=user_id,
            memory_types=all_types,
            limit=limit * 2,
        )
        for r in original_results:
            r["query_source"] = "original"
        sources.append(("original", original_results))
        
        # Fuse results
        weights = {
            "original": 1.0,
            "query_0": 0.9,
            "query_1": 0.7,
            "query_2": 0.5,
        }
        
        fused = self.memory_fuser.fuse(sources, weights)
        
        # Post-process: re-rank by recency if topic changed
        if is_topic_change:
            fused = self._re_rank_by_recency(fused)
        
        # Final filtering
        final_results = self._filter_results(fused, limit)
        
        return final_results
    
    def _re_rank_by_recency(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-rank results by recency for topic changes."""
        now = __import__('datetime').datetime.now()
        
        def recency_score(result: Dict[str, Any]) -> float:
            """Calculate recency score."""
            created_at = result.get("created_at")
            if created_at:
                try:
                    created = __import__('datetime').datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_hours = (now - created).total_seconds() / 3600
                    return max(0, 1.0 - (age_hours / 24))
                except Exception:
                    pass
            return 0.5
        
        # Combine weighted score with recency
        for result in results:
            recency = recency_score(result)
            result["final_score"] = (result.get("weighted_score", 0.0) * 0.6) + (recency * 0.4)
        
        results.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        return results
    
    def _filter_results(
        self,
        results: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Apply final filtering to results."""
        # Remove low-confidence results
        filtered = [r for r in results if r.get("weighted_score", 0.0) > 0.1]
        
        # Limit results
        final = filtered[:limit]
        
        # Add ranking info
        for i, result in enumerate(final):
            result["rank"] = i + 1
        
        return final
    
    async def add_with_context(
        self,
        content: str,
        user_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        memory_type: Optional[MemoryType] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Add memory with automatic type detection based on context.
        
        Args:
            content: Memory content
            user_id: Optional user ID
            context: Optional conversation context
            memory_type: Optional explicit memory type
        
        Returns:
            List of added memory entries
        """
        # Update context analyzer
        if context:
            for msg in context:
                self.context_analyzer.add_message(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                )
        
        # If no explicit type, auto-detect based on context
        if not memory_type:
            memory_type = self._detect_type_from_context(content)
        
        # Add to memory
        return await self.memory.add(
            data=content,
            user_id=user_id,
            memory_type=memory_type,
            **kwargs,
        )
    
    def _detect_type_from_context(self, content: str) -> MemoryType:
        """Detect memory type based on content and context."""
        # Check if this looks like working memory (short, conversational)
        if len(content) < 100:
            # Check recent context for patterns
            recent_content = " ".join(
                msg.get("content", "") for msg in self.context_analyzer.conversation_history[-3:]
            )
            
            # If recent messages are also short, this is likely working memory
            if all(len(msg.get("content", "")) < 200 for msg in self.context_analyzer.conversation_history[-3:]):
                return MemoryType.WORKING
        
        # Fall back to memory's auto-detection
        return None  # None triggers auto-detection in HierarchicalMemory.add()
    
    def clear_context(self) -> None:
        """Clear conversation context."""
        self.context_analyzer.conversation_history.clear()


# Convenience functions
def create_smart_retrieval(memory: HierarchicalMemory) -> SmartMemoryRetrieval:
    """Create a smart memory retrieval instance."""
    return SmartMemoryRetrieval(memory)


async def smart_search(
    memory: HierarchicalMemory,
    query: str,
    user_id: Optional[str] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Convenience function for smart search."""
    retrieval = SmartMemoryRetrieval(memory)
    return await retrieval.retrieve(query, user_id=user_id, **kwargs)