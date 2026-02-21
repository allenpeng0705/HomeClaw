# How to Use LinkedIn Writer (linkedin-writer-1.0.0) in HomeClaw

**linkedin-writer-1.0.0** is an OpenClaw-style **guidance skill**: it has no `run.py` script. The model uses the skill’s **name and description** (and optionally the full **SKILL.md** body) from the “Available skills” block to write LinkedIn posts when you ask.

---

## 1. Make sure skills are enabled

In **config/core.yml**:

```yaml
use_skills: true
skills_dir: config/skills
skills_max_in_prompt: 5   # enough to include linkedin-writer-1.0.0
```

Restart Core after changing config.

---

## 2. Use it by asking in natural language

You don’t call `run_skill` for this skill. Just ask the assistant to write a LinkedIn post. Examples:

- **“Write a LinkedIn post about how we lost our biggest client and what it taught us about customer success.”**
- **“Use the LinkedIn Writer skill to write a post about [topic]. Tone: professional-casual.”**
- **“I need a LinkedIn post for [idea]. Story format, end with a question.”**

The model sees **“LinkedIn Writer (run_skill skill_name: \`linkedin-writer-1.0.0\`): Writes LinkedIn posts that sound like a real person, not a content mill”** in the prompt and will write a post in that style.

---

## 3. What the skill defines (in SKILL.md)

The full **SKILL.md** in this folder contains:

- **Post formats:** Story, Contrarian, List, Lesson Learned, Behind-the-Scenes  
- **Hook formulas** and **formatting rules** (short paragraphs, line breaks, under ~1300 chars, end with a question)  
- **Voice rules** (no buzzwords, first person, contractions, specific > generic)  
- **What to ask the user** (topic, story, takeaway, tone, CTA) and a **quality check** list  

**Currently**, only the **short description** above is injected into the prompt. If you want the **full SKILL.md** (formats, hooks, voice rules) injected so the model follows the guidelines more closely, you can request a config option such as `skills_include_body: true` in Core; then this skill’s full text would be included in “Available skills.”

---

## 4. Optional: vector search for skills

If you enable **skills_use_vector_search** in core.yml, the model retrieves skills by **similarity to your message**. Queries like “write a LinkedIn post” will then tend to pull in **linkedin-writer-1.0.0** when it’s relevant. No change to how you ask—just ask as above.

---

## Summary

| What you do | Example |
|-------------|--------|
| Enable skills | `use_skills: true`, `skills_dir: config/skills` in core.yml |
| Ask for a post | “Write a LinkedIn post about [topic]” or “Use LinkedIn Writer to write…” |
| No run_skill | This skill has no script; the model uses its description (and optionally full SKILL.md) to write the post |

For more formats and templates (e.g. content calendars), see the skill’s README and the context packs link there.
