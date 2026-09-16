# Adaptive Planner

Adaptive Planner is a local-first macOS planner. This app is actively being worked on.

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

The app stores the normal database at `~/Library/Application Support/Adaptive Planner/planner.db`. SQLite is configured for WAL, foreign keys, `synchronous=NORMAL`, and a 5-second busy timeout. A backup is made before migrations, the Settings tab has a consistent `Back Up Now` action, and the five most recent backups are retained. Interrupted startup and corrupt-database recovery are handled explicitly with validation and quarantine of the replaced file.

## v0.1 surface

- PySide6 desktop shell with Today, searchable/filterable Tasks, Calendar, Areas, History, and Settings tabs.
- Timed calendar blocks support drag-to-create, drag-to-move, top/bottom corner or edge resizing, and reversible archival.
- Form-based Quick Capture with Area creation, second-precision estimates, priority, descriptions, and picker-based deadlines.
- Task and Area CRUD, inbox debt, fast remaining-estimate adjustment, completion, defer support, and explicit Area archive/restore actions.
- Native day/week/month calendar views with editable events, overlapping and all-day display, date navigation, drag-to-create ranges, and movable timed events.
- Timed/all-day event validation, date-only deadline semantics, and the permanent built-in `None` Area.
- A readable History tab plus in-app capabilities and keyboard-shortcut help (`⌘⇧H`); Settings opens with `⌘⇧S`.
- Settings can switch all planner date/time behavior to the machine's local timezone.
- Dedicated database worker, explicit phase-gated Alembic foundation migration, immutable DTO boundary, transaction-coupled sparse history events, backup-before-migration, manual backups, startup recovery, single-instance lock, and a read-only Debug inspector toggle (`⌘⇧D` / `Ctrl+Shift+D`).

Scheduler, WorkBlocks, Focus, integrations, and proposal application remain intentionally phase-gated for v0.2+.

## Checks

```bash
uv run pytest
uv run ty check
uv run python -m compileall -q src migrations
```
