---
name: linkedin-writer
description: |
  Writes LinkedIn posts that sound human, not corporate. Generates drafts via run_skill script with API-ready body for maton-api-gateway posting. Use for drafting, saving, and posting LinkedIn content.
trigger:
  patterns: ["linkedin\\s+post|write\\s+(a\\s+)?linkedin|领英|linkedin\\s+content|写.*领英|发.*领英|领英.*写|post\\s+to\\s+linkedin"]
  instruction: |
    The user asked to write a LinkedIn post (draft and/or send). Use run_skill:
      args=["write", "--topic", "<topic>", "--content", "<notes/story>", "--style", "<story|contrarian|list|lesson|behind-the-scenes>", "--tone", "<casual|professional-casual|thought-leader>"]
    The script outputs: post_text, char_count, draft_saved_to, api_body_for_maton, and maton_api_call (app: linkedin, path: rest/posts, method: POST).
    To post directly via maton-api-gateway: use the maton_api_call values from the script output in a subsequent run_skill call.
    If the user only says "write a LinkedIn post" with no topic, ask for the topic before calling the script.
---

# LinkedIn Writer

Writes LinkedIn posts that sound human — no corporate speak, no "I'm humbled to announce." Real thoughts from a real person.

## run_skill

```text
run_skill(skill_name="linkedin-writer-1.0.0", script="request.py",
          args=["write", "--topic", "launching my first product", "--style", "story"])
```

| Argument | Description |
|----------|-------------|
| `--topic` | The main topic or idea of the post |
| `--content` | Optional notes, story, or key points to include |
| `--style` | `story` (default), `contrarian`, `list`, `lesson`, `behind-the-scenes` |
| `--tone` | `casual` (default), `professional-casual`, `thought-leader` |
| `--style list-formats` | List all available formats without writing |

**Output includes:**
- `post_text` — the formatted LinkedIn post ready to copy
- `char_count` — character count (LinkedIn optimal: ≤1300 for reach)
- `draft_saved_to` — path to saved draft (e.g. `output/linkedin-draft-20260425.md`)
- `api_body_for_maton` — JSON body ready for maton-api-gateway POST
- `maton_api_call` — structured call spec for posting (app, path, method, body)

## Sending to LinkedIn (via maton-api-gateway)

After drafting, to post directly:

```text
run_skill(skill_name="maton-api-gateway-1.0.0", script="request.py",
          args=["linkedin", "rest/posts", "POST", "<api_body_from_script>"])
```

Or copy `api_body_for_maton` from the script output into the POST body.

## Post Formats

### 1. The Story Post (default)
Hook → Story (3-5 short paragraphs) → Lesson → Question

### 2. The Contrarian Take
Bold statement → Evidence/reasoning → Nuanced conclusion

### 3. The List Post
Hook → Numbered list (5-10 items) → Brief closer

### 4. The Lesson Learned
"I used to think X. Then Y happened. Now I think Z."

### 5. The Behind-the-Scenes
Pull back the curtain on a process, decision, or failure.

## Hook Formulas

- "Most people get [topic] wrong. Here's what actually works:"
- "I [did something unexpected]. Here's what happened:"
- "[Counterintuitive statement]."
- "Stop doing [common practice]. Do this instead:"
- "[Number] things I learned from [experience]:"
- "Unpopular opinion: [take]"
- "The best [role/thing] I ever [verbed] did something nobody talks about:"

## Formatting Rules

- **Short paragraphs.** 1-2 sentences max per paragraph.
- **Line breaks between every paragraph.** White space is your friend on LinkedIn.
- **No hashtags in the body.** 3-5 max at the bottom if any.
- **No emojis as bullet points.** One emoji per post max.
- **First line is everything.** It shows in preview before "...see more"
- **End with a question.** Drives comments → reach.
- **Under 1300 characters** for optimal engagement.

## Voice Rules

- Write like you talk. Read it out loud — if it sounds stiff, rewrite.
- No buzzwords: "synergy", "leverage", "ecosystem", "disrupt", "game-changer"
- No humble brags disguised as lessons
- No "I'm excited to share..." — just share it
- Specific > generic. "We grew from 12 to 47 customers" beats "significant growth"
- First person. Contractions. "Don't" not "do not."

## Quality Check

- [ ] Hook would make you stop scrolling
- [ ] Sounds like a person, not a brand
- [ ] Has white space (short paragraphs, line breaks)
- [ ] Contains at least one specific detail (numbers, names, dates)
- [ ] Ends with engagement driver (question or clear CTA)
- [ ] No cringe buzzwords
- [ ] Under 1300 characters (unless story format)

## Output

- **Script output:** JSON with `post_text` (for chat), `draft_saved_to` (file link), `api_body_for_maton` (ready for maton-api-gateway), and `maton_api_call` (structured call spec).
- **After posting:** Return the LinkedIn post URL in the reply and note whether it was sent successfully.