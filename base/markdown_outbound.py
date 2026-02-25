"""
Outbound Markdown conversion for channels that cannot display Markdown well.
Use when sending the assistant's reply to an IM so the text looks good.
NEVER raises; on any conversion failure we return the original text so Core never crashes.
See docs_design/OutboundMarkdownAndUnknownRequest.md.
"""

import re
from typing import Optional

# Patterns that suggest the text is Markdown (used to decide whether to convert or pass through as-is).
_MARKDOWN_HINTS = (
    re.compile(r"\*\*[^*]+\*\*"),           # **bold**
    re.compile(r"__[^_]+__"),               # __bold__
    re.compile(r"(?<!\*)\*[^*]+\*(?!\*)"),   # *italic*
    re.compile(r"_[^_]+_"),                  # _italic_
    re.compile(r"~~[^~]+~~"),                # ~~strikethrough~~
    re.compile(r"`[^`]+`"),                  # `code`
    re.compile(r"```[\s\S]*?```"),           # ```block```
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),  # # header
    re.compile(r"\[[^\]]+\]\([^)]+\)"),      # [text](url)
)


def looks_like_markdown(text: str) -> bool:
    """
    Return True if the text appears to contain Markdown (bold, italic, code, headers, links, etc.).
    Used so we only convert when the reply is Markdown; otherwise we send the original text.
    Never raises.
    """
    if not text or not isinstance(text, str):
        return False
    try:
        s = text.strip()
        if not s:
            return False
        for pat in _MARKDOWN_HINTS:
            if pat.search(s):
                return True
        return False
    except Exception:
        return False


def _safe_sub(pat: str, repl, text: str, flags: int = 0) -> str:
    """Run re.sub; on any exception return text unchanged. Never raises."""
    if not text or not isinstance(text, str):
        return text or ""
    try:
        return re.sub(pat, repl, text, flags=flags)
    except Exception:
        return text


def markdown_to_plain(text: str, max_length: Optional[int] = None) -> str:
    """
    Reduce Markdown to readable plain text (strip **, *, _, `, etc.).
    Never raises; on any failure returns the original text (so the channel can send it as-is).
    """
    if not text or not isinstance(text, str):
        return text or ""
    original = text
    try:
        t = text.strip()
        # Remove code blocks first (keep content)
        t = _safe_sub(r"```[\s\S]*?```", lambda m: (m.group(0).replace("```", "").strip() if m else ""), t)
        t = _safe_sub(r"`[^`]+`", lambda m: (m.group(0).strip("`") if m else ""), t)
        # Bold/italic
        t = _safe_sub(r"\*\*([^*]+)\*\*", r"\1", t)
        t = _safe_sub(r"__([^_]+)__", r"\1", t)
        t = _safe_sub(r"\*([^*]+)\*", r"\1", t)
        t = _safe_sub(r"_([^_]+)_", r"\1", t)
        t = _safe_sub(r"~~([^~]+)~~", r"\1", t)
        # Headers
        t = _safe_sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
        # Links
        t = _safe_sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        # Horizontal rule and extra newlines
        t = _safe_sub(r"^[-*_]{3,}\s*$", "", t, flags=re.MULTILINE)
        t = _safe_sub(r"\n{3,}", "\n\n", t)
        t = t.strip()
        if max_length is not None and isinstance(max_length, (int, float)) and len(t) > max_length:
            try:
                t = t[: int(max_length)] + "..."
            except Exception:
                pass
        return t if t else original
    except Exception:
        return original


def markdown_to_whatsapp(text: str) -> str:
    """
    Convert standard Markdown to *bold* _italic_ ~strikethrough~ ```code``` style.
    This format is used by WhatsApp and many other IMs (Telegram, Signal, etc.) that support
    the same markers, so you can use this for any channel that accepts *bold* _italic_ ~strikethrough~.
    Never raises; on any failure returns the original text.
    """
    if not text or not isinstance(text, str):
        return text or ""
    original = text
    try:
        t = text
        # Protect code blocks: replace ```...``` with placeholder, convert, then restore
        code_blocks = []

        def save_code(m):
            try:
                if m is not None and hasattr(m, "group"):
                    code_blocks.append(m.group(0))
                    return "\x00CODE{}\x00".format(len(code_blocks) - 1)
            except Exception:
                pass
            try:
                return m.group(0) if (m is not None and hasattr(m, "group")) else ""
            except Exception:
                return ""

        try:
            t = re.sub(r"```[\s\S]*?```", save_code, t)
        except Exception:
            t = text
        # Bold: **x** or __x__ -> *x*
        t = _safe_sub(r"\*\*([^*]+)\*\*", r"*\1*", t)
        t = _safe_sub(r"__([^_]+)__", r"*\1*", t)
        # Italic: single * or _ -> _x_
        t = _safe_sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"_\1_", t)
        t = _safe_sub(r"_([^_]+)_", r"_\1_", t)
        # Strikethrough: ~~x~~ -> ~x~
        t = _safe_sub(r"~~([^~]+)~~", r"~\1~", t)
        # Restore code blocks
        for i, block in enumerate(code_blocks):
            try:
                t = t.replace("\x00CODE{}\x00".format(i), block)
            except Exception:
                pass
        return t if t else original
    except Exception:
        return original


def markdown_to_channel(text: str, format: str = "plain") -> str:
    """
    Convert Markdown for a channel. format: "plain" | "whatsapp".
    "whatsapp" = *bold* _italic_ ~strikethrough~ (works for WhatsApp, Telegram, Signal, and other IMs that use the same markers).
    Never raises; on any failure returns the original text.
    """
    try:
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return ""
    except Exception:
        return ""
    try:
        fmt = (format or "plain").strip().lower()
        if fmt == "whatsapp":
            return markdown_to_whatsapp(text)
        return markdown_to_plain(text)
    except Exception:
        return text


# Pattern to detect http(s) URLs so we can guarantee link-containing responses use markdown format.
_HTTP_URL = re.compile(r"https?://[^\s]+")


def classify_outbound_format(text: str) -> str:
    """
    Classify how the outbound response should be sent so clients can display correctly.
    Returns one of: "plain" | "markdown".
    - "plain": ordinary text; no markdown rendering.
    - "markdown": content is Markdown or contains an http(s) link; clients should render it so links are clickable.
    Guarantee: if the response contains an http(s) URL, we always return "markdown" so the client can make the link clickable.
    Never raises; on any failure returns "plain".
    """
    try:
        if not text or not isinstance(text, str):
            return "plain"
        s = text.strip()
        if not s:
            return "plain"
        # Guarantee: any response that contains a link uses markdown (or link) format so the link is clickable.
        if _HTTP_URL.search(s):
            return "markdown"
        # Otherwise, if it looks like markdown, client should render it.
        if looks_like_markdown(s):
            return "markdown"
        return "plain"
    except Exception:
        return "plain"
