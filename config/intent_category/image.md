---
id: image
display_name: Images (generate, analyze, send)
enabled: true
priority: 54
classifier_description: "Generate, edit, describe, or OCR an image; vision questions; or send/link an image file when the request is image-centric (画, 截图, 这张图)."

category_tools:
  tools:
  - image
  - get_file_view_link
  - folder_list
  - file_find
  skills:
  - image-generation-1.0.0
---

## Description
The user wants **image-centric work**: **create** art or diagrams, **analyze** or describe a photo/screenshot, read text in an image, *画一个*, *这张图里有什么*, *生成封面*, style transfer or edits routed through image tools. Also **“send me that image”** when it’s clearly about **image files** and image pipeline — if they only need a **generic file link** for a non-image asset, **get_file_link** can win.

## Positive examples
- “Generate a logo with a blue gradient.”
- “What text is visible in this screenshot?”
- “发给我 `images/photo.png` 的预览链接”
- “Draw a simple ER diagram.”
- “Is there a cat in this picture?”
- “Make a 16:9 banner for a blog post.”
- “把这张图改成卡通风格。”
- “识别这张票据图片里的金额和日期。”

## Negative boundaries
- **search_web**: **Find** stock photos or references online — **search_web** unless they ask for **generation** (**image**).
- **read_document**: User cares about **plain text / PDF body**, not pixels or vision.
- **get_file_link**: **Non-image** file (PDF, zip) link-only — **get_file_link**.
- **coding**: Screenshot is **only** context for a **code bug** — **coding** if fixing code is the main ask.

## Workflow hints
- `image` skill/tool; `get_file_view_link`, `folder_list`, `file_find` for locating or sharing assets.
