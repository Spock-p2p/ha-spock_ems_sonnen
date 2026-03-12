Commit all uncommitted changes with an auto-generated descriptive message.

Follow these steps exactly:

1. Run `git status` and `git diff` (staged + unstaged) to understand all pending changes
2. If there are no changes, inform the user and stop
3. Analyze the changes and generate a summary:
   - Group changes by category (views, explores, dashboards, models, features, config, components, translations, etc.)
   - For each file: note if it was added, modified, or deleted
   - Briefly describe what changed in each file
4. Show the summary to the user before committing
5. Stage all changes with `git add -A`
6. Create a commit using conventional commit format (feat/fix/refactor/chore). Include:
   - A concise title line (max 72 chars)
   - A body with the full summary of changes grouped by category
   - A "Files changed" section listing each file with status (Added/Modified/Deleted) and brief description
7. Confirm the commit was created successfully
