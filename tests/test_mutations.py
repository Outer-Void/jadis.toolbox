"""Hard gate: dry-run is zero-mutation, repairs are exact and idempotent, rollback restores, doctor never writes.
These run against a real temporary filesystem (not a fake)."""

import hashlib
import os
import stat
from pathlib import Path

import pytest

from conftest import run_cli
from jadis import repair
from jadis.inspect import Inspection
from jadis.mutations import Authorization, Executor, Mutation, Plan, managed_text, remove_managed
from jadis.system import RealSystem, RunResult


class TmpSystem(RealSystem):
    def __init__(self, home: Path, extra=None):
        self._env = {"HOME": str(home), "PATH": os.environ.get("PATH", ""), "SHELL": "/bin/bash", "XDG_STATE_HOME": str(home / ".state"), **(extra or {})}

    @property
    def env(self):
        return dict(self._env)


def tree(root: Path) -> dict[str, tuple[str, int]]:
    out = {}
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        out[str(p.relative_to(root))] = (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir", stat.S_IMODE(st.st_mode))
    return out


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / ".ssh").mkdir(parents=True)
    (h / ".ssh" / "id_ed25519").write_text("fake key material (not a real key)\n")
    (h / ".ssh" / "id_ed25519.pub").write_text("ssh-ed25519 AAAA test\n")
    os.chmod(h / ".ssh", 0o755)
    os.chmod(h / ".ssh" / "id_ed25519", 0o644)
    (h / ".local" / "bin").mkdir(parents=True)
    (h / ".bashrc").write_text("# my own config\nalias ll='ls -l'\nexport EDITOR=vi\n")
    return h


def apply(system, ids, yes=True):
    plans = repair.plans(Inspection(system), ids)
    ex = Executor(system.env, system.run)
    return [ex.apply(p, Authorization(yes=yes, interactive=False)) for p in plans], ex


def test_dry_run_and_declined_change_nothing(home, monkeypatch):
    system = TmpSystem(home)
    before = tree(home)
    monkeypatch.setenv("HOME", str(home))
    code, out = run_cli(["repair", "--dry-run", "--json"], system)
    assert code == 0 and out["status"] == "planned" and tree(home) == before
    outcomes, _ = apply(system, ["ssh-permissions", "shell-local-bin"], yes=False)
    assert {o.status for o in outcomes} == {"declined"} and tree(home) == before


def test_repairs_are_exact_and_idempotent(home):
    system = TmpSystem(home)
    outcomes, ex = apply(system, ["ssh-permissions", "shell-local-bin"])
    assert all(o.status == "applied" for o in outcomes)
    assert stat.S_IMODE((home / ".ssh").stat().st_mode) == 0o700
    assert stat.S_IMODE((home / ".ssh" / "id_ed25519").stat().st_mode) == 0o600
    assert stat.S_IMODE((home / ".ssh" / "id_ed25519.pub").stat().st_mode) != 0o600  # public key untouched
    rc = (home / ".bashrc").read_text()
    assert rc.startswith("# my own config\nalias ll='ls -l'\nexport EDITOR=vi\n")  # user lines byte-identical
    assert rc.count("# >>> jadis managed: local-bin >>>") == 1
    after = tree(home / ".ssh"), (home / ".bashrc").read_text()
    again, _ = apply(system, ["ssh-permissions", "shell-local-bin"])
    assert {o.status for o in again} == {"nothing-to-do"}
    assert (tree(home / ".ssh"), (home / ".bashrc").read_text()) == after
    journal = [e for e in ex.journal() if e["event"] == "applied"]
    assert {e["kind"] for e in journal} == {"chmod", "managed_block"} and len(journal) == 3


def test_rollback_restores_exact_state(home):
    system = TmpSystem(home)
    original_rc = (home / ".bashrc").read_text()
    outcomes, ex = apply(system, ["ssh-permissions"])
    outcomes += apply(system, ["shell-local-bin"])[0]
    for o in reversed(outcomes):
        plan = ex.rollback_plan(o.run_id)
        assert ex.apply_rollback(plan, Authorization(yes=True)).status == "applied"
    assert stat.S_IMODE((home / ".ssh").stat().st_mode) == 0o755
    assert stat.S_IMODE((home / ".ssh" / "id_ed25519").stat().st_mode) == 0o644
    assert (home / ".bashrc").read_text() == original_rc


def test_managed_block_round_trip_never_touches_user_text():
    user = "line one\nexport PATH=/x:$PATH\n"
    once = managed_text(user, "k", "A=1")
    assert once.startswith(user) and managed_text(once, "k", "A=1") == once
    changed = managed_text(once, "k", "A=2")
    assert changed.startswith(user) and "A=2" in changed and "A=1" not in changed
    assert remove_managed(changed, "k").rstrip("\n") == user.rstrip("\n")


def test_git_repair_uses_argv_and_records_undo(home):
    calls = []
    system = TmpSystem(home)
    ex = Executor(system.env, lambda argv: (calls.append(argv), RunResult(0))[1])
    plan = Plan(
        "t",
        "t",
        [
            Mutation(
                "run",
                "git",
                {"argv": ["git", "config", "--global", "init.defaultBranch", "main"], "undo": ["git", "config", "--global", "--unset", "init.defaultBranch"]},
                True,
                "set",
            )
        ],
    )
    outcome = ex.apply(plan, Authorization(yes=True))
    rb = ex.rollback_plan(outcome.run_id)
    ex.apply_rollback(rb, Authorization(yes=True))
    assert calls == [["git", "config", "--global", "init.defaultBranch", "main"], ["git", "config", "--global", "--unset", "init.defaultBranch"]]


def test_interrupted_operation_is_journaled_and_reported(home):
    system = TmpSystem(home)
    ex = Executor(system.env, lambda argv: RunResult(1, "", "E: dpkg was interrupted"))
    plan = Plan(
        "t", "t", [Mutation("mkdir", str(home / "newdir"), {}, True, "mkdir"), Mutation("run", "apt", {"argv": ["apt-get", "install", "x"]}, False, "install")]
    )
    outcome = ex.apply(plan, Authorization(yes=True))
    assert outcome.status == "failed" and "interrupted" in outcome.error and len(outcome.applied) == 1
    assert [e["event"] for e in ex.journal() if e["run_id"] == outcome.run_id] == ["start", "applied", "failed"]


def test_doctor_env_and_report_perform_zero_mutations(home, monkeypatch, tmp_path):
    system = TmpSystem(home)
    monkeypatch.chdir(tmp_path)
    before, cwd_before = tree(home), tree(tmp_path)
    for argv in (["doctor", "--profile", "full"], ["env", "--json"], ["report", "--json"], ["repair", "--check"]):
        run_cli(argv, system)
    assert tree(home) == before and tree(tmp_path) == cwd_before


def test_bootstrap_dry_run_never_executes(home, monkeypatch):
    from conftest import fixture_system

    s = fixture_system("debian13")
    del s.executables["git"]
    code, out = run_cli(["bootstrap", "minimal", "--dry-run", "--json"], s)
    assert code == 0 and out["status"] == "planned"
    assert not [c for c in s.calls if "apt-get" in " ".join(c)]
