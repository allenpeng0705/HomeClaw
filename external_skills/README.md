# External skills

This folder is used like **skills/** but for converted or experimental skills (e.g. from OpenClaw). Same format: each subfolder has **SKILL.md** and optional **scripts/**.

- **Converted OpenClaw skills:** Put them here first; when a skill is stable and often used, move it to **skills/**.
- **Config:** Default path is `external_skills` (relative to project root). To use a **folder outside the project**, set **external_skills_dir** to an absolute path (e.g. `/opt/skills` or `D:\MySkills`). Set to empty string to disable.

Lookup is the same for all skill dirs: **skills_dir**, then **external_skills_dir**, then **skills_extra_dirs** (first matching folder name wins). See **skills/README.md** and **docs_design/OpenClawSkillsInvestigationAndConverter.md**.
