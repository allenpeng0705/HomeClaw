# How to Use LinkedIn Writer (linkedin-writer-1.0.0) in HomeClaw

**linkedin-writer-1.0.0** has a `scripts/request.py` that can draft posts, save drafts, and produce API-ready bodies for posting via maton-api-gateway.

---

## 1. Enable skills

In **config/core.yml**:

```yaml
use_skills: true
skills_dir: skills
skills_max_in_prompt: 5
```

Restart Core after changing config.

---

## 2. Draft a post

Use **run_skill** with the script:

```text
run_skill(skill_name="linkedin-writer-1.0.0", script="request.py",
          args=["write", "--topic", "launching my first product", "--style", "story"])
```

Optional args:
- `--topic` — the main topic/idea (required)
- `--content` — notes or key points to include
- `--style` — `story` (default), `contrarian`, `list`, `lesson`, `behind-the-scenes`
- `--tone` — `casual` (default), `professional-casual`, `thought-leader`

The script outputs JSON with:
- `post_text` — the formatted post (for chat reply)
- `char_count` — character count (≤1300 optimal for reach)
- `draft_saved_to` — e.g. `output/linkedin-draft-20260425.md`
- `api_body_for_maton` — JSON body ready for maton-api-gateway
- `maton_api_call` — structured call spec (app, path, method, body)

---

## 3. Post to LinkedIn (via maton-api-gateway)

After drafting, use the `maton_api_call` values to post:

```text
run_skill(skill_name="maton-api-gateway-1.0.0", script="request.py",
          args=["linkedin", "rest/posts", "POST", "<api_body>"])
```

Or copy `api_body_for_maton` from the script output into the POST body.

---

## 4. No topic? Ask first

If the user only says "write a LinkedIn post" with no topic, ask for the topic before calling the script. The script requires at least `--topic` or `--content`.

---

## 5. Just drafting, no posting

If the user only wants the draft (not to post), call the script and present `post_text` and `draft_saved_to` in the reply.

---

## Summary

| Goal | How |
|------|-----|
| Draft a post | `run_skill(request.py, ["write", "--topic", "..."])` |
| Get API body for maton | Look at `api_body_for_maton` in script output |
| Post via maton | `run_skill(matton-api-gateway, ["linkedin", "rest/posts", "POST", body])` |
| No topic yet | Ask user for topic first |