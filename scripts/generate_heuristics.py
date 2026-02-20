#!/usr/bin/env python3
"""
Generate heuristic_rules.yml from a verb×noun matrix and/or {{a|b}} templates (Layer 1).

Heuristics use exact substring matching (normalized). Templates like
{{open|launch}} {{browser|app}} expand to all permutations (open browser,
launch app, ...) so you don't type each variant. Avoid greedy {{.*}} in templates.

Principles:
  - Verb+noun or template: specific phrases only (e.g. "search file" vs "search web").
  - Precedence: local rules first, then cloud (first-match-wins).
  - After merge, run scripts/validate_heuristic_rules.py to catch conflicts.

Usage:
  python scripts/generate_heuristics.py [--output PATH] [--merge]
  --merge: merge into config/hybrid/heuristic_rules.yml (existing first; skips conflicting keywords).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def _load_template_expander():
    """Load template_expander without importing hybrid_router package (avoids loguru etc.)."""
    import importlib.util
    path = REPO_ROOT / "hybrid_router" / "template_expander.py"
    if not path.is_file():
        return None, None
    spec = importlib.util.spec_from_file_location("template_expander", path)
    if spec is None or spec.loader is None:
        return None, None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "expand_template", None), getattr(mod, "expand_rule_templates", None)

expand_template, expand_rule_templates = _load_template_expander()

# Action matrix: route -> category -> { verbs, nouns }
# Only verb+noun combinations are emitted (no bare verb/noun) to reduce over-match.
MATRIX = {
    "local": {
        "screen": {
            "verbs": ["take", "capture", "get", "截图", "截取", "抓取", "截"],
            "nouns": ["screenshot", "screen", "window", "display", "图", "屏幕", "快照", "屏"],
        },
        "system": {
            "verbs": ["turn on", "turn off", "open", "close", "start", "stop", "launch", "打开", "关闭", "启动", "停止", "运行"],
            "nouns": ["wifi", "bluetooth", "volume", "brightness", "camera", "mic", "蓝牙", "无线", "音量", "亮度", "相机", "麦克风"],
        },
        "files": {
            "verbs": ["read", "write", "edit", "find", "search", "list", "delete", "move", "读", "写", "找", "搜", "列出", "删", "移动"],
            "nouns": ["file", "folder", "doc", "pdf", "path", "文件", "目录", "文档", "路径", "文件夹"],
        },
        "app": {
            "verbs": ["open", "launch", "start", "close", "quit", "打开", "启动", "关闭", "退出"],
            "nouns": ["app", "application", "browser", "program", "应用", "程序", "浏览器"],
        },
        "lock_sleep": {
            "verbs": ["lock", "unlock", "sleep", "wake", "shut down", "锁", "休眠", "唤醒", "关机", "息屏"],
            "nouns": ["screen", "computer", "pc", "display", "屏幕", "电脑", "显示器"],
        },
        "memory_schedule": {
            "verbs": ["remind", "remember", "record", "schedule", "提醒", "记住", "记录", "定时"],
            "nouns": ["me", "that", "event", "reminder", "我", "日程", "闹钟"],
        },
        "process": {
            "verbs": ["kill", "restart", "check", "list", "show", "结束", "重启", "查看", "列出"],
            "nouns": ["process", "cpu", "memory", "disk", "battery", "进程", "内存", "磁盘", "电池"],
        },
    },
    "cloud": {
        "research": {
            "verbs": ["search", "google", "research", "analyze", "explain", "summarize", "搜索", "查", "分析", "解释", "总结"],
            "nouns": ["web", "internet", "news", "market", "article", "paper", "网页", "网络", "新闻", "市场", "文章", "论文"],
        },
        "reasoning": {
            "verbs": ["explain", "analyze", "compare", "debug", "explain", "解释", "分析", "对比", "调试"],
            "nouns": ["code", "logic", "error", "difference", "代码", "逻辑", "错误", "区别"],
        },
        "creative": {
            "verbs": ["write", "draft", "translate", "brainstorm", "写", "拟稿", "翻译", "头脑风暴"],
            "nouns": ["essay", "email", "post", "story", "文章", "邮件", "推文", "故事"],
        },
    },
}

# Simple conversation → local (greetings, thanks, short replies; no web/reasoning needed)
SIMPLE_CHAT_KEYWORDS = [
    "hello", "hi", "hey", "thanks", "thank you", "bye", "goodbye", "how are you",
    "ok", "okay", "got it", "sounds good", "what's up", "good morning", "good night",
    "你好", "谢谢", "再见", "嗨", "好的", "收到", "早上好", "晚安", "在吗",
]

# Template rules: {{a|b}} expands to all permutations. Be specific (no {{.*}}).
TEMPLATES = [
    {"route": "local", "tmpl": "{{take|capture|get}} {{a |}}screenshot"},
    {"route": "local", "tmpl": "{{打开|启动|运行}}{{浏览器|应用}}"},  # no space for Chinese
    {"route": "local", "tmpl": "{{open|launch|start}} {{the |}}browser"},
    {"route": "local", "tmpl": "{{lock|unlock}} {{the |}}screen"},
    {"route": "cloud", "tmpl": "{{search|google|look up}} {{the |}}web for"},
]


def _is_cjk(s: str) -> bool:
    if not s or not s.strip():
        return False
    return bool(re.search(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", s.strip()))


def _normalize(text: str) -> str:
    import unicodedata
    if not text or not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFC", text.strip().lower())


def _combine(verb: str, noun: str) -> list[str]:
    """Return 'v n' and optionally 'vn' (no space for CJK)."""
    out = [f"{verb} {noun}".strip()]
    if _is_cjk(verb) or _is_cjk(noun):
        out.append(f"{verb}{noun}".strip())
    return out


def _rules_from_templates() -> list[dict]:
    """Expand TEMPLATES ({{a|b}} syntax) to rules with keywords. One rule per tmpl."""
    if not expand_template:
        return []
    rules = []
    for item in TEMPLATES:
        route = (item.get("route") or "local").strip().lower()
        if route not in ("local", "cloud"):
            route = "local"
        tmpl = item.get("tmpl")
        if not tmpl or not isinstance(tmpl, str):
            continue
        phrases = expand_template(tmpl)
        if phrases:
            rules.append({"route": route, "keywords": sorted(phrases)})
    return rules


def generate_rules() -> list[dict]:
    """Build list of { route, keywords } from SIMPLE_CHAT, MATRIX, and TEMPLATES."""
    rules = []
    # Simple conversation first so greetings/short replies route local before any cloud rule
    if SIMPLE_CHAT_KEYWORDS:
        rules.append({"route": "local", "keywords": sorted(SIMPLE_CHAT_KEYWORDS)})
    for route in ("local", "cloud"):
        for _cat_name, components in MATRIX.get(route, {}).items():
            verbs = components.get("verbs") or []
            nouns = components.get("nouns") or []
            keywords = set()
            for v in verbs:
                for n in nouns:
                    for phrase in _combine(v, n):
                        if phrase:
                            keywords.add(phrase)
            if keywords:
                rules.append({"route": route, "keywords": sorted(keywords)})
    rules.extend(_rules_from_templates())
    return rules


def build_config(rules: list[dict], long_input_chars: int = 4000, long_input_route: str = "cloud") -> dict:
    return {
        "long_input_chars": long_input_chars,
        "long_input_route": long_input_route,
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate heuristic rules from verb×noun matrix (Layer 1)."
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=REPO_ROOT / "config" / "hybrid" / "generated_heuristic_rules.yml",
        help="Output YAML path",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge into config/hybrid/heuristic_rules.yml (existing first, then generated; skip conflicting keywords)",
    )
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:
        print("Error: PyYAML required. pip install pyyaml", file=sys.stderr)
        return 1

    generated = generate_rules()
    out_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output

    if args.merge:
        heuristic_path = REPO_ROOT / "config" / "hybrid" / "heuristic_rules.yml"
        existing_rules: list[dict] = []
        long_input_chars = 4000
        long_input_route = "cloud"
        if heuristic_path.is_file():
            try:
                with open(heuristic_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    long_input_chars = int(data.get("long_input_chars") or 4000)
                    long_input_route = str(data.get("long_input_route") or "cloud").strip().lower()
                    if long_input_route not in ("local", "cloud"):
                        long_input_route = "cloud"
                    raw = data.get("rules") or []
                    for r in raw:
                        if not isinstance(r, dict):
                            continue
                        # Expand tmpl to keywords so we don't lose template rules
                        if expand_rule_templates:
                            r = expand_rule_templates(r)
                        kw = r.get("keywords") or []
                        if not kw:
                            continue
                        route = (r.get("route") or "local").strip().lower()
                        if route not in ("local", "cloud"):
                            route = "local"
                        existing_rules.append({
                            "route": route,
                            "keywords": [str(k).strip() for k in kw if k],
                        })
            except Exception:
                pass

        # Keywords already assigned to each route (normalized)
        existing_local_norm = set()
        existing_cloud_norm = set()
        for r in existing_rules:
            for kw in r.get("keywords") or []:
                n = _normalize(kw)
                if not n:
                    continue
                if r.get("route") == "local":
                    existing_local_norm.add(n)
                else:
                    existing_cloud_norm.add(n)

        # Append generated rules; skip any keyword that would conflict with the opposite route
        merged = list(existing_rules)
        for r in generated:
            route = r.get("route", "local")
            keywords = r.get("keywords") or []
            opposite = existing_cloud_norm if route == "local" else existing_local_norm
            added = []
            for kw in keywords:
                n = _normalize(kw)
                if not n:
                    continue
                if n in opposite:
                    continue  # would conflict
                added.append(kw)
                if route == "local":
                    existing_local_norm.add(n)
                else:
                    existing_cloud_norm.add(n)
            if added:
                merged.append({"route": route, "keywords": sorted(added)})

        data = build_config(merged, long_input_chars=long_input_chars, long_input_route=long_input_route)
        heuristic_path.parent.mkdir(parents=True, exist_ok=True)
        with open(heuristic_path, "w", encoding="utf-8") as f:
            f.write("# Layer 1 heuristic rules. Enriched by: python scripts/generate_heuristics.py --merge\n")
            f.write("# First match wins. Run: python scripts/validate_heuristic_rules.py\n\n")
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        total_local = sum(len(r.get("keywords") or []) for r in merged if r.get("route") == "local")
        total_cloud = sum(len(r.get("keywords") or []) for r in merged if r.get("route") == "cloud")
        print(f"Merged into {heuristic_path}: {len(merged)} rules ({total_local} local keywords, {total_cloud} cloud)")
        print("  Run: python scripts/validate_heuristic_rules.py")
        return 0

    data = build_config(generated)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Generated by scripts/generate_heuristics.py. Use --merge to enrich heuristic_rules.yml.\n\n")
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    total_kw = sum(len(r.get("keywords") or []) for r in generated)
    print(f"Generated {len(generated)} rules ({total_kw} keywords) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
