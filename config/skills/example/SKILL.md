---
name: example
description: Example skill to show SKILL.md format. Does nothing by itself; the model can refer to it when use_skills is enabled.
trigger:
  patterns: ["example\\s+skill|show\\s+skill\\s+format"]
  instruction: "User referred to the example skill. This skill is for documentation only; use it to show SKILL.md structure or when use_skills is enabled."
---
This is the optional body. You can add usage notes or instructions here.
The model will see the name and description in the "Available skills" block; body can be included by changing the loader to include_body=True.
