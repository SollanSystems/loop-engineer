# Task Master — Agent Integration Guide

This file is written by `task-master init` so an agent loads Task Master's usage
context automatically. It marks the directory as a Task Master project.

## Essential Commands

```bash
task-master parse-prd .taskmaster/docs/prd.txt   # turn the PRD into a task ledger
task-master list                                 # show every task and its status
task-master next                                 # pick the next unblocked task
task-master show <id>                            # read one task or subtask in full
task-master analyze-complexity                   # score tasks and recommend expansion
task-master expand --id=<id>                     # split a task into subtasks
task-master update-subtask --id=<id> --prompt=…  # append implementation notes
task-master set-status --id=<id> --status=done   # record a task as complete
```

## Key Files

- `.taskmaster/tasks/tasks.json` — the single source of truth for tasks and status; managed by the CLI, never hand-edited.
- `.taskmaster/config.json` — model roles and defaults; change it through `task-master models`.
- `.taskmaster/state.json` — which tag context is active.
- `.taskmaster/docs/prd.txt` — the requirements document that `parse-prd` reads.
- `.taskmaster/tasks/task_NNN.txt` — a human-readable mirror of each task, regenerated from tasks.json.
- `.taskmaster/reports/task-complexity-report.json` — the latest complexity analysis.

## Directory Structure

```
.taskmaster/
├── config.json
├── state.json
├── docs/
│   └── prd.txt
├── tasks/
│   ├── tasks.json
│   └── task_001.txt
├── reports/
│   └── task-complexity-report.json
└── templates/
    └── example_prd.txt
```

## Workflow Loop

1. Read the next task with `task-master show <id>`.
2. Log the plan and progress with `task-master update-subtask --id=<id> --prompt=…`.
3. Implement against the task's own `testStrategy` field.
4. Run that verification and the automated tests before closing the task.
5. Record completion with `task-master set-status --id=<id> --status=done`, which
   also cascades the task's subtasks to done.

The default status flip is a bookkeeping write, not a test gate, so verifying the
`testStrategy` before marking a task done is the discipline that keeps "done"
honest. The optional autopilot workflow adds a code-enforced RED/GREEN/COMMIT gate
whose run-state lives outside this project directory.
