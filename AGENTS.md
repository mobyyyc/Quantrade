# Quantrade Working Agreement

## Task cadence

- Work on one approved roadmap task per run.
- Before starting, state the task being executed.
- After completing a task, report the outcome and state the next task.
- Wait for explicit user approval before starting that next task.

## Roadmap discipline

- Treat `ROADMAP.md` as the authoritative sequence of project work.
- After a small fix, preview, maintenance task, or user-requested detour, return to the next incomplete task in `ROADMAP.md` unless the user explicitly reprioritizes it.
- Do not invent a temporary replacement roadmap from recent conversation context.
- Add, remove, or reorder roadmap tasks only when the user explicitly approves a roadmap change; record that change in `ROADMAP.md` before treating it as the new plan.
- At every handoff, identify the next task by its roadmap ID and title when one exists.

## Change handoff

- When a run changes files, run the relevant checks.
- Stage only the files changed for the approved task.
- Commit the task as a focused Git commit and push it to `origin/main` before handoff.
- Preserve existing user changes and do not use force pushes.
