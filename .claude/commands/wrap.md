Review the current conversation and wrap up the session by doing the following in order:

**1. Update Session Log** (`Session Log.md` at project root):
- Add a new entry at the TOP of the file (most recent first) with today's date
- Sections: What was accomplished, Files created/modified, Next actions (as unchecked `- [ ]` checkboxes)
- Keep all existing entries intact beneath the new one

**2. Update CLAUDE.md** (project root):
- Tick off completed items in "Outstanding" (change `- [ ]` to `- [x]`)
- Add any new outstanding items that emerged this session
- Update "What has been done" if significant new work was completed
- Keep all existing content intact — only add or update what changed

**3. Update memory**:
- Memory for this project lives at `~/.claude/projects/-Users-eapreko--claude-skills-watch/memory/`
- Write or update memories for any new feedback rules, project facts, or reference pointers that emerged
- Keep `MEMORY.md` in that directory as the index (one line per memory file)

**4. Commit to git and push**:
- Stage: `Session Log.md`, `CLAUDE.md`, any new or modified skill files
- Commit message: `Session wrap-up DD Mon YYYY: <one-line summary>`
- Push to remote: `git push git@github-personal:pheistman/claude-watch.git main`
- Unlike the Damian project, pushing is fine here — this repo is public and contains no sensitive data

**5. Report back** with a brief summary: what was updated, what was committed/pushed, and the immediate next action for next session.
