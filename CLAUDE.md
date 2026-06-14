# claude-watch — /watch skill

Multi-provider video transcription skill for Claude Code. Originated from the Damian SEND tribunal project as a need to process Sunshine Academy training videos; spun out as a standalone repo June 2026.

## Repo

- **GitHub:** [pheistman/claude-watch](https://github.com/pheistman/claude-watch)
- **Local:** `~/.claude/skills/watch/`
- **Remote:** `git@github-personal:pheistman/claude-watch.git` (SSH alias for pheistman account)

## What this is

A Claude Code skill that gives Claude the ability to watch videos. Paste a URL or local path; the skill downloads the video, extracts frames, pulls a timestamped transcript (native captions first, then Whisper API fallback), and hands everything to Claude.

**Key differentiators from upstream (`bradautomates/claude-video`):**
- Multi-provider transcription: Groq, AssemblyAI, Deepgram, OpenAI — interchangeable via `--provider`
- File-size-aware auto-selection: audio ≤ 24 MB → Groq; > 24 MB → AssemblyAI → Deepgram (24 MB is the actual Whisper API limit, not a duration proxy)
- Transcript-first pipeline: Claude reads transcript before frame images (15–25× token saving)
- `whisper.py` rewritten in pure stdlib (`urllib`) — no curl subprocess

## Architecture

```
scripts/
  watch.py       — entry point: orchestrates download → frames → transcript → Claude
  whisper.py     — transcription engine; public API:
                   transcribe_video(video_path, audio_out, backend, api_key)
                   → (segments, provider_used) where segments = [{start, end, text}]
                   load_api_key(preferred, file_size_bytes) → (provider_name, api_key)
  download.py    — yt-dlp wrapper
  frames.py      — ffmpeg frame extraction + auto-fps logic
  transcribe.py  — VTT parsing + dedup + Whisper orchestration
  setup.py       — preflight + installer
commands/
  watch.md       — slash command definition (loaded by Claude Code skill system)
hooks/           — SessionStart status hook
```

**Companion file (not in repo):**
- `~/scripts/batch.py` — batch processor for local video libraries; imports `whisper.py` via `sys.path`; delegates all transcription to the watch skill. OUTPUT_BASE points to Damian EHCP/Sunshine Academy directory.

## GitHub conventions

- **Always push as `pheistman`** — remote: `git@github-personal:pheistman/claude-watch.git`
- **Never use `stickeeemmanuel`**
- All GitHub comments, issues, PRs: first person singular ("I/my") — never "we/our"
- Claude can be credited as contributor (Co-Authored-By in commits) but the narrative voice is always "I"

## Upstream relationship

Forked from `bradautomates/claude-video`. Fork notification: bradautomates/claude-video#31.

Open issues engaged:
- **#6** — `allowed-tools` YAML inline-list bug — fixed in this fork (commit `29a7fc9`); comment posted
- **#25** — Long-video support — comment posted pointing to AssemblyAI work
- **#29** — SenseVoice/FunASR — local GPU model, not addressed

## Session log & wrap

Session log: `Session Log.md` (project root)
Wrap command: `/wrap` — `.claude/commands/wrap.md`

## What has been done

- Forked from `bradautomates/claude-video`; README + CHANGELOG rewritten for fork
- `process_sunshine_video.py` → `batch.py`: harmonised; delegates all transcription to `whisper.py` (removed ~150 lines of duplicate curl-based transcription code)
- `whisper.py` rewritten: pure stdlib, 4-provider support, `transcribe_video()` public API
- `watch.py`: `--provider groq|assemblyai|deepgram|openai` added; `--whisper` kept as deprecated alias
- `.gitignore` updated (media files, `.env`)
- Deepgram tested end-to-end via `whisper.py` CLI (548 utterances)
- ggshield scan passed (no secrets); mac-dev-playbook and Ansible task updated for ggshield
- Pushed to `pheistman/claude-watch` — commits `033b3b7` → `29a7fc9`
- `commands/watch.md`: `allowed-tools` inline-list YAML bug fixed
- Fork notification + issue comments posted on `bradautomates/claude-video`
- Routing switched from duration-based (30 min) to file-size-based (24 MB) — actual Whisper API limit; audio extracted before provider selection so size is known at routing time

## Outstanding

- [ ] Manually run `echo "<token>" | ggshield auth login --method=token` on Mac (blocked by auto-mode; token is in Ansible vault at `~/Documents/projects/raspberry-pi/vars/vars.yml`)
- [ ] Evaluate lutzleonhardt's no-download approach: `yt-dlp --skip-download` for captions, audio only as Whisper fallback, frames opt-in — would make ffmpeg optional for captioned sources
- [ ] Consider `--json` output mode (bradautomates/claude-video PR #24 by joweiser)
- [ ] Add frontmatter validation to `build-skill.sh` for `allowed-tools` format (suggested in issue #6)
- [ ] Consider SenseVoice/FunASR as local backend (issue #29) if GPU available
