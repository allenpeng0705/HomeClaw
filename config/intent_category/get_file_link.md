---
id: get_file_link
display_name: Get or send file link
enabled: true
priority: 56
classifier_description: "Get a view or download link for one specific file, or 'send me that file' — deliverable URL, not folder listing and not deep text analysis."

match_patterns:
  - (?i)(send|share)\s+me\s+.+\.(pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|txt|md|csv|zip)\b
  - 发给我\s*.+\.(pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|txt|md|csv|zip)\b

category_tools:
  tools:
  - get_file_view_link
  - folder_list
  - file_find
---

## Description
The user wants a **shareable or downloadable link** for **one (or a few) concrete files**: “send me `report.pdf`”, *发给我*, *把文件发我*, *分享这个附件*, “give me the URL for the screenshot”. Often follows a prior listing. Focus is **URL delivery**, not summarizing the file’s meaning (**read_document**) and not enumerating a whole directory (**list_files**).

## Positive examples
- “Send me a link to `documents/report.pdf`.”
- “发给我 `img1.png`”
- “Share the screenshot in `images/` I mentioned.”
- “Download link for the latest export in `output/`.”
- “Give me a view URL for `share/notes.md`.”
- “把 `output/report.pdf` 发给我。”
- “Send me that image file link from images folder.”

## Negative boundaries
- **list_files**: User only asked **what’s in the folder**, not for a link to one file.
- **read_document**: User wants **summary or Q&A** on content — primary intent is understanding, not the link.
- **image**: User wants to **generate**, **edit**, or **vision-analyze** an image — not only fetch a link (unless “send me that image file” as delivery — can overlap; prefer **get_file_link** when it’s clearly **file delivery**).
- **send_email**: User wants to **email** the file — may combine; if **email** is explicit, **send_email** often wins.
- **search_web** / **news_digest**: “帮我搜新闻发给我” should first retrieve content (web/news). Route here only when a concrete file/path is implied.

## Workflow hints
- Resolve path → `get_file_view_link`; use `folder_list` / `file_find` when the filename is ambiguous.
