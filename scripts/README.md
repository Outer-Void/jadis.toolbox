# Standalone scripts

Personal helpers that predate the `jadis` CLI. They are kept as separate scripts: each one writes data
(logs, repositories, pushes), and the `jadis` CLI only inspects unless explicitly authorized. None is exposed
to BLUX or GOD as a capability; GOD discovers jadis's four read-only capabilities from `.blux/`.

| Script | Purpose | Writes | Network | Verification |
|---|---|---|---|---|
| [`timelog/timelog.sh`](timelog/README.md) | Start/stop time tracking per project; CSV log; plain-text invoice | `~/timelogs`, `~/.config/timelog` | none | `tests/test_scripts.py` (session, CSV safety, portable totals, errors) |
| [`newproject/newproject.sh`](newproject/README.md) | Scaffold a personal project: templates, licence, git init, optional `gh repo create` | `$PROJECTS_DIR/<name>` | only with `--github` | `tests/test_scripts.py` (scaffold, commit identity, literal descriptions, refusals) |
| [`master_log/take-master_log.sh`](master_log/README.md) | Termux:Widget one-tap snapshot: home tree, logcat, battery, processes, ping | shared storage by default (`MASTER_LOG_DIR` overrides; see its privacy note) | `ping 8.8.8.8` | `tests/test_scripts.py` (offline run with tools missing) |
| [`github_backup/github_backup.sh`](github_backup/README.md) | Copy a folder into a private GitHub repository, encrypted with git-crypt | `$BACKUP_DIR`, the remote repository | GitHub | `tests/test_scripts.py` (usage; refuses to push from a locked clone) |

All four pass `shellcheck -S warning` (checked by the same test file when shellcheck is installed).

Outer-Void repositories are created with LRC, not `newproject` (whose default licence is MIT; the
organization's default is proprietary).
