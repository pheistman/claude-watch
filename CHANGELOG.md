# Changelog

All notable changes to `/watch` are documented here.

## [2.0.0] — 2026-06-02

### Added
- Multi-provider transcription: AssemblyAI, Deepgram, Groq, OpenAI
- `--provider groq|assemblyai|deepgram|openai` flag (replaces `--whisper`)
- Duration-aware auto-selection: video < 30 min → Groq; ≥ 30 min → AssemblyAI
- AssemblyAI async upload/poll pipeline — no 25 MB file-size limit
- Deepgram nova-2 synchronous transcription (utterance-level timestamps)
- `setup.py` scaffolds all 4 provider keys in `~/.config/watch/.env`
- `setup.py --check` / `--json` report includes all 4 providers

### Changed
- Transcript-first pipeline: Claude reads the transcript before frame images,
  dramatically reducing token cost for most videos
- `--whisper groq|openai` kept as a deprecated alias for `--provider`
- `whisper.py` rewritten in pure stdlib (no pip deps); multipart upload via
  `urllib` replaces `curl` subprocess calls

### Fixed
- Long-video transcription: AssemblyAI accepts files up to 5 GB, eliminating
  the 25 MB / ~50 min ceiling that affected Groq and OpenAI

## [0.1.3] — 2026-05-09

### Fixed
- Windows: `video.info.json` is read as UTF-8 (#4). Previously `Path.read_text()` defaulted to cp1252 on Windows and crashed on yt-dlp's UTF-8 output, silently dropping Title/Uploader from the report. Same fix applied to `.env` reads/writes in `whisper.py` and `setup.py`.
- `download.py` now logs info.json parse failures to stderr instead of swallowing them.

### Security
- Hardened subprocess argv against option injection (#2): inserted `--` before the URL in the yt-dlp argv, and tightened `is_url` to reject `-`-prefixed sources and require a non-empty netloc. Resolved video/audio paths to absolute via `Path.resolve()` before passing to `ffmpeg`/`ffprobe`, so a relative path starting with `-` can't be misinterpreted as a flag.

## [0.1.2] — 2026-04-24

### Fixed
- Windows console crash: removed the emoji from the long-video warning in `watch.py`; cp1252 consoles couldn't encode it.
- `setup.py` now prints `winget` / `pip` install commands on Windows instead of "unsupported platform" — matches what the README already promised.

### Changed
- `SKILL.md` notes that on Windows the scripts must be invoked with `python`, not `python3` (the latter is the Microsoft Store stub on Windows).

## [0.1.1] — 2026-04-24

### Fixed
- Added `commands/watch.md` shim so `/watch` is callable when installed as a Claude Code plugin. Without it, the plugin loaded but the skill wasn't exposed as a slash command.
- `scripts/build-skill.sh` now strips `commands/` from the claude.ai `.skill` bundle alongside `hooks/` and `.claude-plugin/`.

## [0.1.0] — 2026-04-24

Initial marketplace release.

### Added
- `/watch <url-or-path> [question]` slash command.
- yt-dlp download with native caption extraction (manual + auto-subs).
- ffmpeg frame extraction with auto-scaled fps (≤2 fps, ≤100 frames, duration-aware budget).
- `--start` / `--end` focused mode with denser frame budget and transcript range filtering.
- Whisper fallback (Groq preferred, OpenAI secondary) for videos without captions.
- `setup.py` preflight: silent `--check`, structured `--json`, and installer that auto-runs `brew install` on macOS.
- Session-start hook that prints a one-line status on first run / partial config.
- `.skill` bundle packaging for claude.ai upload via `scripts/build-skill.sh`.
