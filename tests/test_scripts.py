"""The standalone helpers in scripts/: each one runs in an isolated temporary home, offline.

These are the verification path for the utilities outside the `jadis` CLI (see scripts/README.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
TIMELOG = SCRIPTS / "timelog" / "timelog.sh"
NEWPROJECT = SCRIPTS / "newproject" / "newproject.sh"
MASTER_LOG = SCRIPTS / "master_log" / "take-master_log.sh"
GITHUB_BACKUP = SCRIPTS / "github_backup" / "github_backup.sh"
ALL = [TIMELOG, NEWPROJECT, MASTER_LOG, GITHUB_BACKUP]


def run(script: Path, *args: str, env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], env=env, cwd=cwd, capture_output=True, text=True, timeout=60)


def base_env(home: Path) -> dict[str, str]:
    return {"HOME": str(home), "PATH": os.environ["PATH"], "USER": "tester", "LANG": "C.UTF-8", "TZ": "UTC", "TMPDIR": str(home / "tmp"),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_shellcheck_clean():
    result = subprocess.run(["shellcheck", "-S", "warning", *map(str, ALL)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


# --- timelog ----------------------------------------------------------------------------------------------

@pytest.fixture
def tl_env(tmp_path):
    env = base_env(tmp_path)
    env.update(TIMELOG_CONFIG=str(tmp_path / "cfg"), TIMELOG_DIR=str(tmp_path / "logs"))
    (tmp_path / "tmp").mkdir()
    return env


def test_timelog_session_and_portable_invoice(tl_env, tmp_path):
    assert run(TIMELOG, "start", "client-a", "kickoff, with a comma", env=tl_env).returncode == 0
    assert run(TIMELOG, "start", "other", env=tl_env).returncode == 1  # one session at a time
    assert "client-a" in run(TIMELOG, "status", env=tl_env).stdout
    assert run(TIMELOG, "stop", "done", env=tl_env).returncode == 0
    rows = (tmp_path / "logs" / "timelog.csv").read_text().splitlines()
    assert [len(r.split(",")) for r in rows] == [9, 10]  # the comma in the note did not shift columns
    assert "kickoff; with a comma" in rows[0]
    out = run(TIMELOG, "invoice", "client-a", env=tl_env)  # default path honours TMPDIR (Termux has no /tmp)
    assert out.returncode == 0, out.stderr
    invoice = next((tmp_path / "tmp").glob("invoice-client-a-*.txt")).read_text()
    assert "Total Sessions: 1" in invoice and "Total Time: 00:00:0" in invoice


def test_timelog_errors(tl_env):
    assert run(TIMELOG, "stop", env=tl_env).returncode == 1
    assert run(TIMELOG, "start", env=tl_env).returncode == 1
    assert run(TIMELOG, "invoice", "nothing-logged", env=tl_env).returncode == 1
    assert run(TIMELOG, "bogus", env=tl_env).returncode == 2
    assert run(TIMELOG, "help", env=tl_env).returncode == 0


# --- newproject -------------------------------------------------------------------------------------------

def test_newproject_creates_a_committed_project(tmp_path):
    env = base_env(tmp_path) | {"PROJECTS_DIR": str(tmp_path / "p")}
    out = run(NEWPROJECT, "demo_tool", "-d", "Uses $(literal) text", "-t", "python", "-u", "Tester", "-e", "tester@example.com", env=env)
    assert out.returncode == 0, out.stdout + out.stderr
    proj = tmp_path / "p" / "demo_tool"
    assert {"README.md", "LICENSE", ".gitignore", "setup.py"} <= {p.name for p in proj.iterdir()}
    assert "Uses $(literal) text" in (proj / "README.md").read_text()  # descriptions are never executed
    log = subprocess.run(["git", "-C", str(proj), "log", "--format=%an <%ae>"], capture_output=True, text=True, env=env)
    assert log.stdout.strip() == "Tester <tester@example.com>"


def test_newproject_refusals(tmp_path):
    env = base_env(tmp_path) | {"PROJECTS_DIR": str(tmp_path / "p")}
    assert run(NEWPROJECT, "bad name!", "-u", "T", "-e", "t@example.com", env=env).returncode == 1
    assert run(NEWPROJECT, "dup", "-n", "-u", "T", "-e", "t@example.com", env=env).returncode == 0
    assert run(NEWPROJECT, "dup", "-n", "-u", "T", "-e", "t@example.com", env=env).returncode == 1  # never overwrites


# --- master_log ----------------------------------------------------------------------------------------------

def test_master_log_offline_with_missing_tools(tmp_path):
    """Only basic tools on PATH: logcat, termux-api, ping and tree are absent, and each is recorded as skipped."""
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("bash", "sh", "date", "awk", "mkdir", "find", "xargs", "ls", "basename", "stat", "wc", "grep", "cat", "printf"):
        found = shutil.which(name)
        if found:
            (tools / name).symlink_to(found)
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "notes.txt").write_text("x")
    env = base_env(tmp_path / "home") | {"PATH": str(tools), "MASTER_LOG_DIR": str(tmp_path / "out")}
    out = subprocess.run([str(tools / "bash"), str(MASTER_LOG)], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    master = (tmp_path / "out" / "logs" / "master.log").read_text()
    for skipped in ("logcat", "termux-battery-status", "ping"):
        assert f"[MISSING] command '{skipped}' not found" in master
    tree = next((tmp_path / "out" / "logs").glob("master-log-tree-*.log")).read_text()
    assert "notes.txt" in tree


# --- github_backup -----------------------------------------------------------------------------------------

def test_github_backup_usage():
    assert run(GITHUB_BACKUP, env=base_env(Path("/nonexistent"))).returncode == 1


def test_github_backup_refuses_plaintext_push_from_a_locked_clone(tmp_path):
    """A cloned repository that asks for git-crypt but is not unlocked must never receive a commit."""
    env = base_env(tmp_path) | {"GIT_USER_NAME": "Tester", "GIT_USER_EMAIL": "tester@example.com", "GITHUB_USER": "tester",
                                "BACKUP_DIR": str(tmp_path / "backups"), "INCLUDE_HOSTNAME": "0"}
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True, env=env)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(remote), str(seed)], check=True, env=env)
    (seed / ".gitattributes").write_text("* filter=git-crypt diff=git-crypt\n.gitattributes !filter !diff\n")
    for cmd in (["add", ".gitattributes"], ["-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init"], ["push", "-q", "origin", "main"]):
        subprocess.run(["git", "-C", str(seed), *cmd], check=True, env=env)
    head_before = subprocess.run(["git", "-C", str(remote), "rev-parse", "main"], capture_output=True, text=True, env=env).stdout

    # git-crypt stub: `status` succeeds (the repository is git-crypt-managed); nothing else is available.
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "git-crypt").write_text("#!/bin/sh\n[ \"$1\" = status ] && exit 0\nexit 1\n")
    (stub / "git-crypt").chmod(0o755)
    env["PATH"] = f"{stub}:{env['PATH']}"
    env["GIT_REMOTE"] = str(remote)

    secret = tmp_path / "src"
    secret.mkdir()
    (secret / "private.txt").write_text("do not leak")
    out = run(GITHUB_BACKUP, "src", "backups-repo", env=env, cwd=tmp_path)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "would be pushed unencrypted" in out.stdout
    head_after = subprocess.run(["git", "-C", str(remote), "rev-parse", "main"], capture_output=True, text=True, env=env).stdout
    assert head_after == head_before  # nothing reached the remote
    log = subprocess.run(["git", "-C", str(remote), "log", "--all", "-p"], capture_output=True, text=True, env=env).stdout
    assert "do not leak" not in log
