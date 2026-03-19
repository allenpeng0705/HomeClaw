#!/usr/bin/env python3
"""Tiny hook for run_skill: reminds the agent to use builtin tools per SKILL.md.

The actual research must be done via tavily_research, web_search, fetch_url, etc.—not this script.
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    topic = " ".join(sys.argv[1:]).strip() or "(no topic in args)"
    payload = {
        "skill": "deep-research-workflow",
        "topic": topic,
        "next_steps": [
            "Call tavily_research(input=<question>) if Tavily Research API is configured, else web_search + fetch_url.",
            "Respect search budgets and finish with inline [1][2] citations and a ### Sources section.",
            "Read external_skills/deep-research-workflow/SKILL.md for the full workflow.",
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
