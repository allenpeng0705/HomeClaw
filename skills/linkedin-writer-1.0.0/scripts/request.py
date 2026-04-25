#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
LinkedIn Writer skill script for HomeClaw run_skill.

Usage:
  request.py write --topic "<topic>" [--content "<content>"] [--style <story|contrarian|list|lesson|behind-the-scenes>] [--tone <casual|professional-casual|thought-leader>]
  request.py list-formats

write: Generate a LinkedIn post and save draft. Returns the post text and API-ready JSON body.
list-formats: Print available post format styles.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

_HOOK_FORMULAS = [
    "Most people get {topic} wrong. Here's what actually works:",
    "I [did something unexpected]. Here's what happened:",
    "[Counterintuitive statement].",
    "Stop doing [common practice]. Do this instead:",
    "[Number] things I learned from [experience]:",
    "Unpopular opinion: [take]",
    "The best [role/thing] I ever [verbed] did something nobody talks about:",
    "I used to think X. Then Y happened. Now I think Z.",
]

_STORY_TEMPLATE = """{hook}

{story_paragraphs}

{lesson}

{question}"""

_STYLES = {
    "story": {
        "description": "Hook → Story (3-5 short paragraphs) → Lesson → Question",
        "sections": 5,
    },
    "contrarian": {
        "description": "Bold statement that challenges conventional wisdom → Evidence → Nuanced conclusion",
        "sections": 3,
    },
    "list": {
        "description": "Hook → Numbered list (5-10 items) → Brief closer",
        "sections": 3,
    },
    "lesson": {
        "description": '"I used to think X. Then Y happened. Now I think Z."',
        "sections": 3,
    },
    "behind-the-scenes": {
        "description": "Pull back the curtain on a process, decision, or failure.",
        "sections": 4,
    },
}

_DEFAULT_OUTPUT_DIR = "output"


def _output_dir() -> Path:
    out_env = (os.environ.get("HOMECLAW_OUTPUT_DIR") or "").strip()
    if out_env:
        p = Path(out_env).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = (Path.cwd() / _DEFAULT_OUTPUT_DIR).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_post(topic: str, content: str, style: str, tone: str) -> str:
    """Build a LinkedIn post given topic + optional content/notes."""
    topic = (topic or "").strip()
    style = (style or "story").strip().lower()
    tone = (tone or "casual").strip().lower()

    if style not in _STYLES:
        style = "story"

    hook = _HOOK_FORMULAS[0].replace("{topic}", topic) if "{topic}" in _HOOK_FORMULAS[0] else _HOOK_FORMULAS[1].replace("[did something unexpected]", f"launched {topic}")

    if style == "story":
        body = content if content.strip() else f"""We made a mistake that cost us our biggest account last quarter.

Not because we lacked process — we had all the dashboards, all the check-ins, all the "best practices."

But we were measuring activity instead of outcomes.

The fix wasn't a new framework. It was getting back in the room with the customer and asking the stupid questions we thought we were above.

Three months later? That account is back. And our NRR is up 18 points.

The lesson: the basics work. You just have to actually do them."""

        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        lesson = "\n\nThe lesson: keep the basics basic. Measure outcomes, not activity."
        question = "\n\nWhat's one customer touchpoint you might be over-engineering?"

    elif style == "contrarian":
        hook_text = f"Unpopular opinion: most {topic} advice is written by people who've never actually done it."
        evidence = """
The problem:
- Theory sounds clean
- Reality is messy
- Every proven framework has a long list of caveats nobody mentions

The real answer is usually boring. Do the work. Talk to customers. Iterate."""

        body = f"{hook_text}\n\n{evidence}"
        lesson = ""
        question = '\n\nWhat\'s a "best practice" in your field that\'s actually over-rated?'

    elif style == "list":
        items = content.split("\n") if content.strip() else [
            "Define success before you start",
            "Know your audience's actual pain points",
            "Write the ending first",
            "Cut the first paragraph every time",
            "Ship it, then improve it",
        ]
        bullet_items = []
        for i, item in enumerate(items[:8], 1):
            item = item.strip().strip("-").strip()
            if item:
                bullet_items.append(f"{i}. {item}")

        body = f"{_HOOK_FORMULAS[4].replace('[Number]', str(len(bullet_items))).replace('[experience]', topic)}\n\n" + "\n".join(bullet_items)
        lesson = ""
        question = "\n\nWhich one would you add? 👇"

    elif style == "lesson":
        body = f"""I used to think {topic} was about discipline.

Then I watched a team of naturally disciplined people fail because they were optimizing for the wrong thing.

The shift wasn't about doing more. It was about deciding what less would mean.

Now when I look at any initiative, the first question is: what does success actually look like — not in outputs, but in outcomes?

What changed for me was realizing that clarity beats intensity every time."""
        lesson = ""
        question = "\n\nWhat's something you had to unlearn to get better at this?"

    else:  # behind-the-scenes
        hook_text = f"Here's what nobody tells you about {topic}:"
        inner = content if content.strip() else f"""We spent 6 months building something.

The version that shipped looked nothing like the version we designed.

Not because we compromised — because reality has a way of editing your best plans.

The prototype nobody liked became the product thousands use every week.

The lesson: done and imperfect beats perfect and unwritten."""

        body = f"{hook_text}\n\n{inner}"
        lesson = ""
        question = "\n\nWhat's something you've learned the hard way? Drop it below."

    post_parts = [hook, ""]
    if body:
        post_parts.append(body.strip())
    if lesson:
        post_parts.append(lesson.strip())
    if question:
        post_parts.append(question.strip())

    return "\n".join(post_parts)


def cmd_list_formats() -> int:
    print("## Available LinkedIn post formats\n")
    for name, info in _STYLES.items():
        print(f"### {name}")
        print(f"   {info['description']}\n")
    print("Default style: story")
    return 0


def cmd_write(topic: str, content: str, style: str, tone: str) -> int:
    if not topic and not content:
        print(json.dumps({"success": False, "error": "At least one of --topic or --content is required"}, ensure_ascii=False))
        return 1

    post = _build_post(topic, content, style, tone)
    char_count = len(post)
    trimmed = char_count > 1300
    preview_truncated = post[:600] + ("..." if len(post) > 600 else "")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"linkedin-draft-{ts}.md"
    out_dir = _output_dir()
    out_path = out_dir / filename

    try:
        out_path.write_text(post, encoding="utf-8")
        out_rel = f"output/{filename}"
    except Exception as e:
        out_path = out_dir / "linkedin-draft.md"
        out_path.write_text(post, encoding="utf-8")
        out_rel = "output/linkedin-draft.md"

    # API-ready body for maton-api-gateway POST to linkedin/rest/posts
    api_body = {
        "commentary": post,
        "visibility": "PUBLIC",
    }

    result = {
        "success": True,
        "post_text": post,
        "char_count": char_count,
        "trimmed_to_fit": trimmed,
        "style": style,
        "tone": tone,
        "draft_saved_to": out_rel,
        "api_body_for_maton": json.dumps(api_body, ensure_ascii=False),
        "maton_api_call": {
            "app": "linkedin",
            "path": "rest/posts",
            "method": "POST",
            "body": api_body,
        },
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  request.py write --topic '<topic>' [--content '<notes>'] [--style <style>] [--tone <tone>]", file=sys.stderr)
        print("  request.py list-formats", file=sys.stderr)
        return 1

    cmd = sys.argv[1].strip().lower()

    if cmd == "list-formats":
        return cmd_list_formats()

    if cmd == "write":
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--topic", default="", help="Post topic/idea")
        p.add_argument("--content", default="", help="Optional notes/story content")
        p.add_argument("--style", default="story", help="story|contrarian|list|lesson|behind-the-scenes")
        p.add_argument("--tone", default="casual", help="casual|professional-casual|thought-leader")
        args = p.parse_args(sys.argv[2:])
        return cmd_write(args.topic, args.content, args.style, args.tone)

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())