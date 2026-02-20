#!/usr/bin/env python3
"""
Utterance Factory: generate dense local/cloud example utterances for Layer 2 semantic router.

Two mechanisms:
  - Template expansion: verb + object sets → many combinations (e.g. 打开+浏览器, find+file).
  - Expert list: hand-curated phrases that can't be expressed as simple verb+object.

Why this helps Layer 2:
  - Density: more utterances give the embedding space a larger, continuous "region" for each intent.
  - Disambiguation: local stresses file/folder/device; cloud stresses web/search/explain/write.
  - Multilingual: both 找文件 and find file so the model aligns Chinese and English.

Usage:
  python scripts/generate_utterances.py [--output PATH] [--max-local N] [--max-cloud N]
  Default output: config/hybrid/generated_utterances.yml
  Recommended: keep local in 300–500 to balance accuracy vs latency (~10ms vs 50ms).

How to use the output:
  - Option A (use generated file): set hybrid_router.semantic.routes_path to
    config/hybrid/generated_utterances.yml in config/core.yml. No copying.
  - Option B (enrich semantic_routes): run with --merge to merge generated
    utterances into config/hybrid/semantic_routes.yml (keeps existing + adds generated).
  - Option C (replace): run with -o config/hybrid/semantic_routes.yml to overwrite
    semantic_routes.yml with only the generated lists.

Bad-things avoidance: keep local under 300–500 so embedding lookup stays fast (~10ms).
When you add new plugins (e.g. Spotify), add verbs/objects to LOCAL_TEMPLATES and re-run.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Template categories: verbs + objects → local intent
# ---------------------------------------------------------------------------
LOCAL_TEMPLATES = {
    "file_ops": {
        "verbs": [
            "find", "search", "list", "delete", "move", "copy", "compress",
            "找", "搜索", "列出", "删除", "移动", "复制", "压缩",
        ],
        "objects": [
            "file", "folder", "document", "image", "pdf", "screenshot",
            "文件", "文件夹", "文档", "图片", "截图",
        ],
    },
    "sys_ctrl": {
        "verbs": [
            "turn on", "turn off", "mute", "unmute", "increase", "decrease",
            "打开", "关闭", "调高", "调低", "切换", "静音",
        ],
        "objects": [
            "volume", "brightness", "bluetooth", "wifi", "microphone", "display",
            "音量", "亮度", "蓝牙", "麦克风", "屏幕",
        ],
    },
    "screen_device": {
        "verbs": [
            "capture", "screenshot", "lock", "sleep", "wake", "hide", "show",
            "截图", "截屏", "锁屏", "休眠", "唤醒", "隐藏", "显示",
        ],
        "objects": [
            "screen", "window", "desktop", "current window", "monitor",
            "屏幕", "窗口", "桌面", "当前窗口",
        ],
    },
    "app_launch": {
        "verbs": [
            "open", "launch", "start", "run", "close", "quit",
            "打开", "启动", "运行", "关闭", "退出",
        ],
        "objects": [
            "app", "application", "browser", "browser window", "program",
            "应用", "程序", "浏览器",
        ],
    },
    "memory_schedule": {
        "verbs": [
            "remind", "remember", "record", "schedule", "list", "search",
            "提醒", "记住", "记录", "定时", "列出", "查",
        ],
        "objects": [
            "me", "that", "this", "event", "reminder", "calendar",
            "我", "这个", "日程", "闹钟", "日历",
        ],
    },
    "process_system": {
        "verbs": [
            "kill", "restart", "check", "list", "show", "monitor",
            "结束", "重启", "查看", "列出", "显示", "监控",
        ],
        "objects": [
            "process", "cpu", "memory", "disk", "battery", "temperature",
            "进程", "内存", "磁盘", "电池", "温度", "网速",
        ],
    },
}

# Hand-curated local intents (not expressible as simple verb+object)
LOCAL_EXPERT = [
    # Simple conversation (chit-chat → local; no web/reasoning)
    "hi",
    "hello",
    "hey",
    "how are you",
    "thanks",
    "thank you",
    "bye",
    "goodbye",
    "ok",
    "got it",
    "sounds good",
    "what's up",
    "just saying hi",
    "你好",
    "谢谢",
    "再见",
    "嗨",
    "好的",
    "收到",
    "早上好",
    "晚安",
    "take a screenshot",
    "capture the window",
    "截图",
    "截个图",
    "lock my computer",
    "put the pc to sleep",
    "锁屏",
    "进入休眠",
    "check cpu usage",
    "which app is lagging",
    "看看哪个程序卡了",
    "sync to cloudflare r2",
    "rclone push",
    "同步到 R2",
    "同步到 R2 存储",
    "what time is it",
    "几点了",
    "remind me in 5 minutes",
    "五分钟后提醒我",
    "search my chat history",
    "search for files matching",
    "在本地找文件",
    "list files in this folder",
    "列出当前目录",
    "compress this folder into zip",
    "压缩成 zip",
    "move screenshots to Pictures",
    "把截图移到图片文件夹",
    "show my local IP",
    "显示本机 IP",
    "eject the usb drive",
    "安全弹出 U 盘",
    "mute the microphone",
    "关闭麦克风",
    "turn brightness up",
    "调高亮度",
    "git log last 3 commits",
    "看看 git 最近三次提交",
    "start local llama server",
    "启动本地 llama 服务",
]

# Hand-curated cloud intents (web search, explain, write, translate, plan)
CLOUD_EXPERT = [
    "search the web for the latest news",
    "search the web for",
    "google the price of bitcoin",
    "网上搜一下新闻",
    "explain quantum physics simply",
    "how does a turbocharger work",
    "解释一下量子物理",
    "write a python script for a chatbot",
    "debug this java code",
    "帮我写一段代码",
    "translate this paragraph to german",
    "how to say hello in spanish",
    "翻译成德语",
    "plan a trip to japan",
    "itinerary for london",
    "策划一下去日本的旅行",
    "summarize this long article",
    "give me a gist of this page",
    "总结这篇文章",
    "what are the top stock trends today",
    "最新比特币价格",
    "find me a recipe for",
    "搜一下最新的 AI 论文",
    "explain the differences between Kafka and RabbitMQ",
    "分析这段代码的优缺点",
    "write a short essay about",
    "帮我写一篇关于 AI 的文章",
    "translate this to French",
    "把这段话翻译成法语",
    "brainstorm 10 ideas for",
    "头脑风暴一下",
    "what happened in the world today",
    "今天有什么大新闻",
    "summarize the latest tech news",
    "总结今天推特上的热门话题",
    "explain quantum entanglement to a 5-year-old",
    "解释量子力学的基本原理",
    "write a formal email to my boss",
    "帮我写一封正式的道歉邮件",
    "what is the current price of Bitcoin in USD",
    "现在比特币多少钱",
    "find the official documentation for React",
    "帮我查一下签证要求",
]


def _is_cjk(s: str) -> bool:
    """True if string contains CJK characters (used for no-space variant)."""
    if not s or not s.strip():
        return False
    return bool(re.search(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", s.strip()))


def _combine(verb: str, obj: str) -> list[str]:
    """Return one or two phrases: 'v o' and optionally 'vo' for Chinese."""
    out = [f"{verb} {obj}".strip()]
    if _is_cjk(verb) or _is_cjk(obj):
        out.append(f"{verb}{obj}".strip())
    return out


def generate_local_from_templates(max_combinations: int | None = 800) -> set[str]:
    """Generate local utterances from verb+object templates. Capped to avoid explosion."""
    seen: set[str] = set()
    for category in LOCAL_TEMPLATES.values():
        verbs = category.get("verbs") or []
        objects = category.get("objects") or []
        for v in verbs:
            for o in objects:
                for phrase in _combine(v, o):
                    if phrase and phrase not in seen:
                        seen.add(phrase)
                        if max_combinations and len(seen) >= max_combinations:
                            return seen
    return seen


def generate(
    max_local: int = 500,
    max_cloud: int = 300,
    max_local_from_templates: int = 450,
) -> tuple[list[str], list[str]]:
    """
    Build final local and cloud utterance lists.
    - Local: LOCAL_EXPERT first, then template combinations until total <= max_local.
    - Cloud: CLOUD_EXPERT only (no template expansion for cloud by default), capped at max_cloud.
    """
    local_set: set[str] = set()
    for u in LOCAL_EXPERT:
        if u and u.strip():
            local_set.add(u.strip())

    from_templates = generate_local_from_templates(max_combinations=max_local_from_templates)
    remaining = max(0, max_local - len(local_set))
    for u in sorted(from_templates):
        if len(local_set) >= max_local:
            break
        if u and u.strip() and u.strip() not in local_set:
            local_set.add(u.strip())

    cloud_set: set[str] = set()
    for u in CLOUD_EXPERT:
        if u and u.strip():
            cloud_set.add(u.strip())
    cloud_list = sorted(cloud_set)[:max_cloud]

    return (sorted(local_set)[:max_local], cloud_list)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate local/cloud utterances for semantic router (Layer 2)."
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=REPO_ROOT / "config" / "hybrid" / "generated_utterances.yml",
        help="Output YAML path (default: config/hybrid/generated_utterances.yml)",
    )
    parser.add_argument(
        "--max-local",
        type=int,
        default=500,
        help="Max local utterances (default 500; 300–500 recommended for latency)",
    )
    parser.add_argument(
        "--max-cloud",
        type=int,
        default=300,
        help="Max cloud utterances (default 300)",
    )
    parser.add_argument(
        "--max-from-templates",
        type=int,
        default=450,
        help="Max local utterances from verb+object templates (default 450)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge generated into config/hybrid/semantic_routes.yml (existing + generated, deduped)",
    )
    args = parser.parse_args()

    local_list, cloud_list = generate(
        max_local=args.max_local,
        max_cloud=args.max_cloud,
        max_local_from_templates=args.max_from_templates,
    )

    try:
        import yaml
    except ImportError:
        print("Error: PyYAML required. pip install pyyaml", file=sys.stderr)
        return 1

    out_path = args.output
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    if args.merge:
        semantic_path = REPO_ROOT / "config" / "hybrid" / "semantic_routes.yml"
        existing_local: list[str] = []
        existing_cloud: list[str] = []
        if semantic_path.is_file():
            try:
                with open(semantic_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    existing_local = list(data.get("local_utterances") or data.get("local") or [])
                    existing_cloud = list(data.get("cloud_utterances") or data.get("cloud") or [])
                    existing_local = [str(u).strip() for u in existing_local if u]
                    existing_cloud = [str(u).strip() for u in existing_cloud if u]
            except Exception:
                pass

        def _dedupe_by_canonical(items: list[str]) -> list[str]:
            """Dedupe by normalized form (strip + lower); keep first occurrence."""
            seen: set[str] = set()
            out: list[str] = []
            for u in items:
                key = u.strip().lower() if u else ""
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(u.strip())
            return out

        raw_local = _dedupe_by_canonical(existing_local + local_list)
        raw_cloud = _dedupe_by_canonical(existing_cloud + cloud_list)
        local_keys = {u.strip().lower() for u in raw_local}
        # Remove from cloud any phrase that already appears in local (avoid cross-list duplicates)
        merged_cloud = [u for u in raw_cloud if u.strip().lower() not in local_keys]
        merged_local = sorted(raw_local)
        merged_cloud = sorted(merged_cloud)
        if len(raw_cloud) != len(merged_cloud):
            print(f"  (removed {len(raw_cloud) - len(merged_cloud)} cloud phrase(s) that were also in local)", file=sys.stderr)

        data = {
            "local_utterances": merged_local,
            "cloud_utterances": merged_cloud,
        }
        semantic_path.parent.mkdir(parents=True, exist_ok=True)
        with open(semantic_path, "w", encoding="utf-8") as f:
            f.write("# Layer 2 semantic router. Enriched by: python scripts/generate_utterances.py --merge (deduped within and across lists).\n")
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"Merged into {semantic_path}: {len(merged_local)} local, {len(merged_cloud)} cloud (no duplicates)")
        return 0

    data = {
        "local_utterances": local_list,
        "cloud_utterances": cloud_list,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Auto-generated by scripts/generate_utterances.py. Use --merge to enrich semantic_routes.yml.\n")
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(local_list)} local and {len(cloud_list)} cloud utterances -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
