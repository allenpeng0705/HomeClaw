# Downloads (ClawHub staging)

This folder is the **staging directory** for `clawhub install`. When you install a skill from ClawHub (OpenClaw’s registry), the raw OpenClaw skill is downloaded here (e.g. `downloads/skills/<skill_id>/`). HomeClaw then **converts** it and writes the result to `external_skills/<skill_id>/`, which is what Core loads.

- **You don’t load skills from here.** Core only loads from `skills/` and `external_skills/`.
- Configure the path in `config/core.yml`: `clawhub_download_dir: downloads` (default).
- Safe to add `downloads/` to `.gitignore` if you don’t want to commit downloaded OpenClaw skills.
