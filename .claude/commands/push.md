Smart push: commit all changes, sync with remote, push, and ensure PR exists with professional description.

Follow these steps exactly:

1. Detect the current git branch name (use `git branch --show-current`)
2. Run `git status` to check for changes
3. If there are uncommitted changes:
   - Stage all changes with `git add -A`
   - Analyze the diff to auto-generate a descriptive commit message summarizing what changed
   - Include a "Files changed" section at the end of the commit body listing each file with status and description
4. Sync with remote: run `git pull --rebase origin <current-branch>`
   - If there are conflicts, stop and report them to the user
5. Push: run `git push origin <current-branch>`
6. Check if a PR already exists for this branch: `gh pr view --json number,title,url 2>/dev/null`
   - If NO PR exists, create one with `gh pr create` following the format below
   - If a PR already exists, report its URL
7. Report success

## PR creation format

When creating a PR:
- Run `git log main..HEAD --oneline` and `git diff main...HEAD --stat` to understand all changes
- Title: conventional commit style, max 70 chars (e.g. "feat: Add Sonnen battery EMS integration")
- Body must include:
  1. **Summary**: 3-5 bullet points describing what changed and why
  2. **Test plan**: checklist of verification steps
  3. **Files changed**: table grouped by category (components, config, translations, etc.) with Status (Added/Modified/Deleted) and Description per file
  4. Footer: `Generated with [Claude Code](https://claude.com/claude-code)`
