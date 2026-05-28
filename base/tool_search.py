"""
Tool Search System (inspired by OpenClaw)

Implements intelligent tool discovery with:
- Semantic search scoring
- Keyword matching
- Description analysis
- Usage-based ranking

Scoring algorithm:
- Exact name/id match: +20 points
- Name includes term: +8 points
- ID includes term: +6 points
- Label includes term: +4 points
- Description includes term: +2 points
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from base.tools import ToolDefinition, get_tool_registry


@dataclass
class ToolSearchResult:
    """Result of a tool search."""
    tool_name: str
    score: float
    match_type: str  # "exact", "name", "keyword", "description", etc.
    tool_definition: Optional[ToolDefinition] = None


class ToolSearchEngine:
    """
    Search engine for tools with intelligent scoring.
    
    Features:
    - Multi-factor scoring algorithm
    - Fuzzy matching support
    - Keyword extraction from descriptions
    - Code mode for JavaScript-based discovery
    """
    
    def __init__(self):
        self._registry = get_tool_registry()
        self._search_count = 0
        self._describe_count = 0
        self._call_count = 0
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent matching."""
        return query.lower().strip()
    
    def _score_tool(
        self,
        tool: ToolDefinition,
        query: str,
        query_tokens: List[str],
    ) -> Tuple[float, str]:
        """
        Score a tool against a query.
        
        Returns (score, match_type)
        """
        score = 0.0
        match_types: List[str] = []
        
        name = (tool.name or "").lower()
        description = (tool.description or "").lower()
        short_desc = (tool.short_description or "").lower()
        
        query_norm = self._normalize_query(query)
        
        # Exact name match
        if name == query_norm:
            score += 20.0
            match_types.append("exact")
        
        # Name includes query terms
        if query_norm in name:
            score += 8.0
            match_types.append("name")
        
        # Description matching
        if query_norm in description:
            score += 2.0
            match_types.append("description")
        
        if query_norm in short_desc:
            score += 3.0  # Slightly higher weight for short description
            match_types.append("short_description")
        
        # Token-based matching
        for token in query_tokens:
            if len(token) < 2:
                continue
            
            if token in name:
                score += 2.0
            if token in description:
                score += 1.0
            if token in short_desc:
                score += 1.5
        
        # Parameter name matching
        params = tool.parameters.get("properties", {}) if isinstance(tool.parameters, dict) else {}
        for param_name, param_schema in params.items():
            param_name_lower = param_name.lower()
            if query_norm in param_name_lower:
                score += 1.0
                match_types.append("parameter")
            
            # Check parameter description
            param_desc = (param_schema.get("description") or "").lower()
            if query_norm in param_desc:
                score += 0.5
        
        # Determine primary match type
        if "exact" in match_types:
            primary_match = "exact"
        elif "name" in match_types:
            primary_match = "name"
        elif "short_description" in match_types:
            primary_match = "short_description"
        elif "description" in match_types:
            primary_match = "description"
        elif "parameter" in match_types:
            primary_match = "parameter"
        else:
            primary_match = "partial"
        
        return (score, primary_match)
    
    def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 1.0,
    ) -> List[ToolSearchResult]:
        """
        Search for tools matching the query.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            min_score: Minimum score threshold for results
        
        Returns:
            List of ToolSearchResult sorted by score (descending)
        """
        self._search_count += 1
        
        if not query or not isinstance(query, str):
            return []
        
        query_norm = self._normalize_query(query)
        query_tokens = query_norm.split()
        
        results: List[ToolSearchResult] = []
        tools = self._registry.list_tools()
        
        for tool in tools:
            score, match_type = self._score_tool(tool, query_norm, query_tokens)
            
            if score >= min_score:
                results.append(ToolSearchResult(
                    tool_name=tool.name,
                    score=score,
                    match_type=match_type,
                    tool_definition=tool,
                ))
        
        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        
        # Apply limit
        return results[:limit]
    
    def describe_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a tool."""
        self._describe_count += 1
        
        tool = self._registry.get(tool_name)
        if not tool:
            return None
        
        return {
            "name": tool.name,
            "description": tool.description,
            "short_description": tool.short_description,
            "parameters": tool.parameters,
            "risk_tier": tool.risk_tier,
            "requires_confirmation": tool.requires_confirmation,
            "max_retries": tool.max_retries,
        }
    
    def list_all_tools(self) -> List[Dict[str, Any]]:
        """List all available tools with their metadata."""
        tools = self._registry.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "short_description": tool.short_description,
                "risk_tier": tool.risk_tier,
            }
            for tool in tools
        ]
    
    def get_usage_stats(self) -> Dict[str, int]:
        """Get search/describe/call usage statistics."""
        return {
            "search_count": self._search_count,
            "describe_count": self._describe_count,
            "call_count": self._call_count,
        }
    
    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._search_count = 0
        self._describe_count = 0
        self._call_count = 0


# Global search engine instance
_search_engine: Optional[ToolSearchEngine] = None


def get_tool_search_engine() -> ToolSearchEngine:
    """Return the global tool search engine."""
    global _search_engine
    if _search_engine is None:
        _search_engine = ToolSearchEngine()
    return _search_engine


def search_tools(
    query: str,
    limit: int = 10,
    min_score: float = 1.0,
) -> List[ToolSearchResult]:
    """Convenience function to search tools."""
    return get_tool_search_engine().search(query, limit, min_score)


def describe_tool(tool_name: str) -> Optional[Dict[str, Any]]:
    """Convenience function to describe a tool."""
    return get_tool_search_engine().describe_tool(tool_name)


def list_available_tools() -> List[Dict[str, Any]]:
    """Convenience function to list all tools."""
    return get_tool_search_engine().list_all_tools()


# Example usage patterns
# ----------------------
# search_tools("read file") -> Returns tools related to file reading
# search_tools("web search") -> Returns web search tools
# describe_tool("file_read") -> Returns detailed info about file_read
# list_available_tools() -> Returns all tools with metadata
