# File and folder structure (summary)

Quick reference so file listing, reading, and links work reliably.

---

## Two roots only

| You want…           | Use path      | Resolves to              |
|---------------------|---------------|---------------------------|
| **My files**        | `""` or `"."` or a subfolder name | `homeclaw_root/{your_user_id}/` (or `.../companion/` when not tied to a user) |
| **Shared folder**   | `share` or `share/...`            | `homeclaw_root/share/`    |

Everything else (workspace, config, etc.) is not for user file access. File tools only see these two trees.

---

## Standard subfolders under “My files”

Under your sandbox root the system expects (and the assistant uses) these names. You can create them if missing:

| Subfolder       | Typical use                          |
|-----------------|--------------------------------------|
| **output/**     | Generated reports, slides, exports   |
| **documents/**  | PDFs, Word, etc.                     |
| **downloads/**  | Downloaded files                     |
| **images/**     | Images, photos                       |
| **work/**       | Work files                           |
| **knowledge/**     | Files indexed for search (RAG)   |

Paths are always **relative** to one of the two roots (e.g. `documents/1.pdf`, `output/report.html`, `share/readme.pdf`). Never use absolute paths (no `C:\`, `/Users/`, etc.).

---

## Why “not found” happens and how to avoid it

- **List then read/link:** After `folder_list()` or `file_find()`, use the **path** value from the result in `document_read(path='...')` or `get_file_view_link(path='...')`. Do **not** use only the **name** (e.g. `1.pdf`) if the result says `path: documents/1.pdf`—otherwise the file may not be found.
- **Same path, same tool:** The path returned by list/find is exactly what read/link expect. If you pass a different path (e.g. invented or from another message), resolution can fail.
- **User/scope:** Files are per user (or companion). If the request user changes, the sandbox root changes; a path that worked for one user may not exist for another.

---

## Simplification

- **Only two roots:** “My files” (sandbox) and “Share”. No need to remember more.
- **Subfolders are conventions:** `output/`, `documents/`, etc. are recommended names; you can use others. The assistant is instructed to use these so paths stay consistent.
- **Config:** Set **`homeclaw_root`** in **config/core.yml** (e.g. `D:/homeclaw`). When empty, file tools return a clear error.

See also: [Per-user sandbox and file links](per-user-sandbox-and-file-links.md), [FileSandboxDesign.md](../docs_design/FileSandboxDesign.md).
