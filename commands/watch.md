---
description: Watch a video (URL or local path). Downloads with yt-dlp, extracts frames with ffmpeg, transcribes from captions or Whisper, and answers questions about what's in the video.
argument-hint: <video-url-or-path> [question]
allowed-tools: Bash, Read, AskUserQuestion
---

Invoke the `watch` skill (defined in SKILL.md) with the user's arguments: $ARGUMENTS

Follow the skill's full pipeline: preflight setup check → download via yt-dlp → extract frames + transcript → **read transcript first** → assess whether transcript alone can answer the question → read frames only if needed → answer the user. If the user provided no arguments, ask them for a video URL or local path before proceeding.
