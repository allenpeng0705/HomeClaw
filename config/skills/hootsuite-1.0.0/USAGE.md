# How to ask (Hootsuite skill)

- "What are my Hootsuite social profiles?" (run `list` to get profile IDs)
- "Post to X and Facebook via Hootsuite: Hello world"
- "Schedule a Hootsuite post for 3pm tomorrow UTC: [message]"
- "Post to my Hootsuite LinkedIn profile: …"

You need a **Hootsuite subscription** and **HOOTSUITE_ACCESS_TOKEN** (or `hootsuite_access_token` in this skill's config.yml). Get the token via OAuth at [developer.hootsuite.com](https://developer.hootsuite.com). Use **list** first to get social profile IDs, then **post** with one or more IDs (comma-separated). Scheduled time must be at least 5 minutes in the future (UTC, ISO-8601).
