"""
Layer 2: Semantic router using aurelio-labs/semantic-router with existing local embedding.
Custom encoder calls Util().embedding() (llama.cpp embedding server); no second embedding model.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import yaml

# Optional import: Layer 2 only used when semantic is enabled
try:
    from semantic_router import SemanticRouter
    from semantic_router.route import Route
    from semantic_router.encoders.base import DenseEncoder
    _has_semantic_router = True
except ImportError:
    SemanticRouter = None  # type: ignore
    Route = None  # type: ignore
    DenseEncoder = None  # type: ignore
    _has_semantic_router = False


def _ensure_semantic_router():
    if not _has_semantic_router:
        raise ImportError(
            "Layer 2 semantic router requires 'semantic-router'. Install with: pip install semantic-router"
        )


if _has_semantic_router:

    class HomeClawEmbeddingEncoder(DenseEncoder):  # type: ignore[name-defined]
        """
        DenseEncoder that uses the existing HomeClaw embedding (Util().embedding() -> llama.cpp).
        Implements __call__ and acall for sync and async use by the router.
        """
        type: str = "homeclaw"

        async def _embed_docs(self, docs: List[Any]) -> List[List[float]]:
            from base.util import Util
            out = []
            for d in docs:
                text = str(d).strip() if d is not None else ""
                if not text:
                    if out:
                        out.append([0.0] * len(out[0]))
                    else:
                        vec = await Util().embedding(" ")
                        out.append(vec if isinstance(vec, list) else [0.0] * 384)
                    continue
                vec = await Util().embedding(text)
                if vec is None or not isinstance(vec, list):
                    if out:
                        out.append([0.0] * len(out[0]))
                    else:
                        out.append([0.0] * 384)
                else:
                    out.append(vec)
            return out

        def __call__(self, docs: List[Any]) -> List[List[float]]:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                return asyncio.run(self._embed_docs(docs))
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._embed_docs(docs))
                return future.result()

        async def acall(self, docs: List[Any]) -> List[List[float]]:
            return await self._embed_docs(docs)


else:
    HomeClawEmbeddingEncoder = None  # type: ignore[misc, assignment]


def _default_local_utterances() -> List[str]:
    return [
        "take a screenshot",
        "lock the screen",
        "open the browser",
        "turn off the display",
        "what time is it",
        "remind me in 5 minutes",
        "截图", "锁屏", "打开应用",
    ]


def _default_cloud_utterances() -> List[str]:
    return [
        "search the web for",
        "what is the latest news",
        "summarize this article",
        "translate this to French",
        "write a short essay about",
        "网上搜索", "实时新闻", "翻译",
    ]


def load_semantic_routes(
    routes_path: Optional[str] = None,
    root_dir: Optional[Path] = None,
    local_utterances: Optional[List[str]] = None,
    cloud_utterances: Optional[List[str]] = None,
) -> Tuple[List[Any], List[Any]]:
    """
    Load route utterances for local and cloud. Returns (local_utterances, cloud_utterances).
    If routes_path is set and valid YAML, use it; else use local_utterances/cloud_utterances or defaults.
    """
    if routes_path and root_dir:
        path = Path(routes_path)
        if not path.is_absolute():
            path = Path(root_dir) / path
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    loc = data.get("local_utterances") or data.get("local")
                    cloud = data.get("cloud_utterances") or data.get("cloud")
                    if isinstance(loc, list) and isinstance(cloud, list):
                        return ([str(u) for u in loc if u], [str(u) for u in cloud if u])
            except Exception:
                pass
    loc = local_utterances if isinstance(local_utterances, list) and local_utterances else _default_local_utterances()
    cloud = cloud_utterances if isinstance(cloud_utterances, list) and cloud_utterances else _default_cloud_utterances()
    return (loc, cloud)


# Cache one router instance per process (keyed by routes_path or "default")
_semantic_router_cache: Dict[str, Any] = {}


def build_semantic_router(
    encoder: Optional[Any] = None,
    local_utterances: Optional[List[str]] = None,
    cloud_utterances: Optional[List[str]] = None,
    routes_path: Optional[str] = None,
    root_dir: Optional[Path] = None,
    use_cache: bool = True,
) -> Any:
    """Build SemanticRouter with Route('local', ...) and Route('cloud', ...). Uses encoder or creates HomeClawEmbeddingEncoder."""
    _ensure_semantic_router()
    cache_key = routes_path or "default"
    if use_cache and cache_key in _semantic_router_cache:
        return _semantic_router_cache[cache_key]
    loc, cloud = load_semantic_routes(
        routes_path=routes_path,
        root_dir=root_dir,
        local_utterances=local_utterances,
        cloud_utterances=cloud_utterances,
    )
    if encoder is None:
        encoder = HomeClawEmbeddingEncoder(name="homeclaw")
    routes = [
        Route(name="local", utterances=loc),
        Route(name="cloud", utterances=cloud),
    ]
    router = SemanticRouter(encoder=encoder, routes=routes)
    if use_cache:
        _semantic_router_cache[cache_key] = router
    return router


async def run_semantic_layer_async(
    query: str,
    router: Any,
    threshold: float = 0.5,
) -> Tuple[float, Optional[str]]:
    """
    Run Layer 2 semantic router on user message. Uses router.acall(query).
    Returns (score, selection). selection is 'local' | 'cloud' or None.
    Map route name to selection; use similarity_score if available and compare to threshold.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return (0.0, None)
    try:
        choice = await router.acall(text=query.strip(), limit=1)
    except Exception:
        return (0.0, None)
    if choice is None:
        return (0.0, None)
    # choice can be RouteChoice or list when limit > 1
    if isinstance(choice, list):
        choice = choice[0] if choice else None
    if choice is None:
        return (0.0, None)
    name = getattr(choice, "name", None)
    if name not in ("local", "cloud"):
        return (0.0, None)
    score = getattr(choice, "similarity_score", None)
    if score is None:
        score = 1.0
    score = float(score)
    if score < threshold:
        return (0.0, None)
    return (score, name)
