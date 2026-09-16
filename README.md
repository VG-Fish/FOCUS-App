# Adaptive Planner

Adaptive Planner is a local-first macOS planner. This repository contains the usable v0.1 foundation described in `Adaptive_Planner_Proposal.md`.

## Run

```bash
uv venv .venv
uv sync --dev
uv run adaptive-planner
```

For a disposable development database:

```bash
uv run adaptive-planner --db /tmp/adaptive-planner.db
```

The app stores the normal database at `~/Library/Application Support/Adaptive Planner/planner.db`. SQLite is configured for WAL, foreign keys, `synchronous=NORMAL`, and a 5-second busy timeout. A backup is made before migrations and the five most recent backups are retained.

## v0.1 surface

- PySide6 desktop shell with Today, Inbox, Calendar, Areas, and Settings tabs.
- Form-based Quick Capture with Area creation, estimates, priority, descriptions, and picker-based deadlines.
- Task and Area CRUD, inbox debt, fast remaining-estimate adjustment, completion, defer support, and explicit Area archival actions.
- Native day/week/month calendar views with editable events, overlapping and all-day display, date navigation, and double-click time blocking.
- Timed/all-day event validation, date-only deadline semantics, and the permanent built-in `None` Area.
- A readable History tab plus in-app capabilities and keyboard-shortcut help (`⌘⇧H`); Settings opens with `⌘⇧S`.
- Settings can switch all planner date/time behavior to the machine's local timezone.
- Dedicated database worker, Alembic foundation migration, immutable DTO boundary, transaction-coupled sparse history events, backup-before-migration, single-instance lock, and a Debug inspector toggle (`⌘⇧D` / `Ctrl+Shift+D`).

Scheduler, WorkBlocks, Focus, integrations, and proposal application remain intentionally phase-gated for v0.2+.

## Checks

```bash
uv run pytest
uv run ty check
uv run python -m compileall -q src migrations
```
