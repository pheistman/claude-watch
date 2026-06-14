# Session Log

---

## Session: 14 June 2026
**Topics:** upstream issue triage, file-size routing, transcription provider selection

### What was accomplished
- Triaged new activity on `bradautomates/claude-video`: lutzleonhardt's independent no-download fork (comment on #31), drlee91's Deepgram PR #35, issue #25 closed with joweiser abandoning upstream, Kosmo1 confirming the `allowed-tools` bug on #6
- Switched transcription provider routing from duration-based (30 min threshold) to file-size-based (24 MB threshold) — the actual Whisper constraint, not a proxy for it
- For audio > 24 MB, provider order changed to `assemblyai → deepgram → groq → openai` (groq/openai demoted since they 413 on large files)
- Audio extraction moved inside `transcribe_video` before provider selection, so file size is known at routing time
- `duration_seconds` parameter removed from `transcribe_video` and `load_api_key`; watch.py pre-check updated to drop duration arg

### How key problems were solved
- Duration as a routing proxy → file size as routing trigger: file size is the actual Whisper API constraint; duration at 64 kbps could vary (30 min ≈ 14 MB, well under the limit). Borrowed the trigger from drlee91's PR #35, kept our AssemblyAI backend.

### New critical findings
1. lutzleonhardt independently built a fork that never downloads the video — captions only via `yt-dlp --skip-download`, audio download only as Whisper fallback, frames opt-in with `--frames`. Strong signal that transcript-first / no-download is the right default.
2. joweiser concluded Brad is not actively maintaining the upstream repo (published as YouTube demo, not a maintained project) — no point waiting for upstream merges.

### Immediate next actions
- [ ] Evaluate lutzleonhardt's no-download approach (`yt-dlp --skip-download` for captions, audio only as fallback) — could skip ffmpeg as a hard dependency for captioned sources

---

## 2026-06-02 — Fork execution + multi-provider launch

### Accomplished
- Executed full fork plan from `FORK-PLAN.md`
- `process_sunshine_video.py` → `batch.py`: harmonised to delegate all transcription to `whisper.py`; removed ~150 lines of duplicate curl-based transcription code
- `whisper.py` rewritten in pure stdlib (`urllib`): 4-provider support (Groq, AssemblyAI, Deepgram, OpenAI); `transcribe_video()` and `load_api_key()` as public API
- `watch.py`: `--provider groq|assemblyai|deepgram|openai` flag added; `--whisper` kept as deprecated alias
- Deepgram tested end-to-end via `whisper.py` CLI — 548 utterances returned ✓
- ggshield 1.51.0 installed via `gitguardian/tap`; `secret scan repo` passed — no secrets ✓
- Repo created as `pheistman/claude-watch` on GitHub; pushed via `git@github-personal` (SSH alias)
- Fork notification posted: bradautomates/claude-video#31
- `commands/watch.md`: fixed `allowed-tools` YAML inline-list bug (CC slash-command parser rejects `[...]` syntax); pushed as `29a7fc9`
- Commented on bradautomates/claude-video#6 (bug confirmed + fix live in fork) and #25 (long-video: AssemblyAI work pointed out)
- mac-dev-playbook updated: `gitguardian/tap` tap + `gitguardian/tap/ggshield` package
- Ansible `ggshield.yml`: auth task amended to `echo "{{ ggshield_token }}" | ggshield auth login --method=token` with `no_log: true`

### Files created / modified
- `~/.claude/skills/watch/scripts/whisper.py` — rewritten (pure stdlib, 4 providers)
- `~/.claude/skills/watch/scripts/watch.py` — `--provider` flag added
- `~/.claude/skills/watch/.gitignore` — media files + `.env` patterns added
- `~/.claude/skills/watch/README.md` — rewritten for pheistman fork
- `~/.claude/skills/watch/CHANGELOG.md` — v2.0.0 entry added
- `~/.claude/skills/watch/commands/watch.md` — `allowed-tools` bug fixed
- `~/.claude/skills/watch/CLAUDE.md` — created (this session)
- `~/.claude/skills/watch/Session Log.md` — created (this session)
- `~/.claude/skills/watch/.claude/commands/wrap.md` — created (this session)
- `~/scripts/batch.py` — renamed from `process_sunshine_video.py`; harmonised
- `~/Documents/projects/mac-dev-playbook/config.yml` — ggshield added
- `~/Documents/projects/raspberry-pi/tasks/ggshield.yml` — auth task amended

### Next actions
- [ ] Manually run `echo "<token>" | ggshield auth login --method=token` on Mac (auto-mode blocked raw token; token in Ansible vault)
- [ ] Consider `--json` output mode (bradautomates/claude-video PR #24 by joweiser) — useful for skill-chaining
- [ ] Add frontmatter validation to `build-skill.sh` for `allowed-tools` format (suggested in issue #6)
- [ ] Consider SenseVoice/FunASR as a local backend option (issue #29)
