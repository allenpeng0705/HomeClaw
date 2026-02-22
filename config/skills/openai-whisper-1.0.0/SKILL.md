---
name: openai-whisper
description: Local speech-to-text with the Whisper CLI (no API key).
homepage: https://openai.com/research/whisper
trigger:
  patterns: ["transcribe|whisper|speech\\s+to\\s+text|语音转文字|转写|transcription"]
  instruction: "The user asked to transcribe audio. Use run_skill(skill_name='openai-whisper-1.0.0', ...) or run whisper CLI with audio path; --model, --output_format, --task translate. See skill body."
---

# Whisper (CLI)

Use `whisper` to transcribe audio locally.

Quick start
- `whisper /path/audio.mp3 --model medium --output_format txt --output_dir .`
- `whisper /path/audio.m4a --task translate --output_format srt`

Notes
- Models download to `~/.cache/whisper` on first run.
- `--model` defaults to `turbo` on this install.
- Use smaller models for speed, larger for accuracy.
