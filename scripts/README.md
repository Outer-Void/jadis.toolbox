# Standalone scripts

Personal helpers that predate the `jadis` CLI. They are kept as separate scripts: each one writes data
(logs, repositories, pushes), and the `jadis` CLI only inspects unless explicitly authorized. None is exposed
to BLUX or GOD as a capability; GOD discovers jadis's four read-only capabilities from `.blux/`.

| Script | Purpose | Writes | Network | Verification |
|---|---|---|---|---|
| [`timelog/timelog.sh`](timelog/README.md) | Start/stop time tracking per project; CSV log; plain-text invoice | `~/timelogs`, `~/.config/timelog` | none | `tests/test_scripts.py` (session, CSV safety, portable totals, errors) |
| [`newproject/newproject.sh`](newproject/README.md) | Scaffold a personal project: templates, licence, git init, optional `gh repo create` | `$PROJECTS_DIR/<name>` | only with `--github` | `tests/test_scripts.py` (scaffold, commit identity, literal descriptions, refusals, proprietary default, valid `package.json`) |
| [`master_log/take-master_log.sh`](master_log/README.md) | Termux:Widget one-tap snapshot: home tree, logcat, battery, processes, optional ping | private `~/.local/state/jadis/master_log/logs` (owner-only) by default; `MASTER_LOG_DIR` overrides | `ping 8.8.8.8` only with `MASTER_LOG_PING=1` | `tests/test_scripts.py` (offline run with tools missing, private default, opt-ins) |
| [`github_backup/github_backup.sh`](github_backup/README.md) | Copy a folder into a private GitHub repository, encrypted with git-crypt | `$BACKUP_DIR`, the remote repository | GitHub | `tests/test_scripts.py` (usage; refuses to push from a locked clone) |

All four pass `shellcheck -S warning` (checked by the same test file when shellcheck is installed).

Outer-Void repositories are created with LRC, not `newproject`, which is a personal bootstrapper. Its default
licence is proprietary, like the organization's (owner decision, OV-54, 2026-11-07); `-l MIT` and the other
listed licences are available, and an unknown licence is refused.
