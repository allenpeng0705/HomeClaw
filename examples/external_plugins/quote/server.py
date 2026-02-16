"""
External Quote Plugin - HTTP server with multiple capabilities.
Run: python -m examples.external_plugins.quote.server
Then register with Core: python -m examples.external_plugins.quote.register
Core POSTs PluginRequest (with capability_id and capability_parameters) to /run; server dispatches by capability_id.
"""
import random
import uvicorn
from fastapi import FastAPI
from typing import Dict, Any

app = FastAPI()

QUOTES = [
    ("The only way to do great work is to love what you do.", "Steve Jobs", "motivation"),
    ("Innovation distinguishes between a leader and a follower.", "Steve Jobs", "innovation"),
    ("Stay hungry, stay foolish.", "Steve Jobs", "motivation"),
    ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt", "dreams"),
    ("It is during our darkest moments that we must focus to see the light.", "Aristotle", "perseverance"),
    ("Success is not final, failure is not fatal.", "Winston Churchill", "success"),
    ("The only impossible journey is the one you never begin.", "Tony Robbins", "motivation"),
]


@app.get("/health")
def health():
    return {"status": "ok"}


def _get_random_quote(topic: str = None, style: str = None) -> str:
    if topic:
        topic_lower = topic.lower()
        filtered = [q for q in QUOTES if topic_lower in (q[2] or "").lower()]
        pool = filtered if filtered else QUOTES
    else:
        pool = QUOTES
    quote, author, _ = random.choice(pool)
    if style and style.lower() == "short":
        return f'"{quote}" — {author}'
    return f'Quote: "{quote}"\nAuthor: {author}'


@app.post("/run")
async def run(body: Dict[str, Any]):
    """Accept PluginRequest (JSON), dispatch by capability_id, return PluginResult (JSON)."""
    request_id = body.get("request_id", "")
    plugin_id = body.get("plugin_id", "quote")
    cap_id = (body.get("capability_id") or "get_quote").strip().lower().replace(" ", "_")
    params = body.get("capability_parameters") or {}
    topic = (params.get("topic") or "").strip() or None
    style = (params.get("style") or "").strip() or None

    if cap_id == "get_quote_by_topic":
        text = _get_random_quote(topic=topic, style=style)
    else:
        # get_quote (default)
        text = _get_random_quote(topic=None, style=style)

    return {
        "request_id": request_id,
        "plugin_id": plugin_id,
        "success": True,
        "text": text,
        "error": None,
        "metadata": {},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3101)
