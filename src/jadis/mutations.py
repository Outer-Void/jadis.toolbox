"""What exactly will change? The only module that changes the machine.

Flow for every repair, bootstrap, venv creation and restore:
    inspect -> Plan (exact mutations, each marked reversible or not) -> show it -> authorize -> execute
    -> verify -> journal.

- A plan is data. `--dry-run`/`--plan` print it and stop; the executor is never reached.
- Execution needs explicit authorization: `--yes`, or a "y" typed at an interactive terminal. A
  non-interactive run without `--yes` changes nothing (exit 4).
- Files are backed up before they are written. Managed edits touch only a marked block, never the user's own
  lines.
- Every applied mutation is journaled (XDG state dir). `jadis repair --rollback RUN` reverses a run from that
  journal.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jadis.system import RunResult

BEGIN = "# >>> jadis managed: {name} >>>"
END = "# <<< jadis managed: {name} <<<"


@dataclass
class Mutation:
    kind: str  # chmod | managed_block | mkdir | run
    target: str
    detail: dict[str, Any]
    reversible: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    plan_id: str
    title: str
    mutations: list[Mutation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.mutations

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "mutations": [m.to_dict() for m in self.mutations],
            "notes": self.notes,
            "reversible": all(m.reversible for m in self.mutations),
        }


def state_dir(env: dict[str, str]) -> Path:
    base = env.get("XDG_STATE_HOME") or os.path.join(env.get("HOME", "."), ".local", "state")
    return Path(base) / "jadis"


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def managed_text(existing: str, name: str, body: str) -> str:
    """Return `existing` with the named managed block set to `body`. Text outside the block is untouched."""
    begin, end = BEGIN.format(name=name), END.format(name=name)
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    if begin in existing and end in existing:
        head, _, rest = existing.partition(begin)
        _, _, tail = rest.partition(end)
        return head + block.rstrip("\n") + tail if tail.startswith("\n") else head + block + tail
    sep = "" if not existing or existing.endswith("\n") else "\n"
    return existing + sep + ("\n" if existing else "") + block


def remove_managed(existing: str, name: str) -> str:
    begin, end = BEGIN.format(name=name), END.format(name=name)
    if begin not in existing:
        return existing
    head, _, rest = existing.partition(begin)
    _, _, tail = rest.partition(end)
    return (head.rstrip("\n") + "\n" if head.strip() else "") + tail.lstrip("\n")


class Authorization:
    def __init__(self, yes: bool, interactive: bool | None = None, prompt: Callable[[str], str] | None = None):
        self.yes = yes
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.prompt = prompt or input

    def granted(self, plan: Plan) -> bool:
        if self.yes:
            return True
        if not self.interactive:
            return False
        answer = self.prompt(f"Apply {len(plan.mutations)} change(s) for '{plan.title}'? [y/N] ")
        return answer.strip().lower() in ("y", "yes")


@dataclass
class Outcome:
    run_id: str | None
    applied: list[dict[str, Any]]
    status: str  # applied | declined | nothing-to-do | failed
    error: str | None = None


class Executor:
    """Applies plans. `runner` executes `run` mutations (argv, no shell)."""

    def __init__(self, env: dict[str, str], runner: Callable[[list[str]], RunResult]):
        self.env = env
        self.runner = runner
        self.state = state_dir(env)

    def _journal(self, entry: dict[str, Any]) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / "journal.jsonl").open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def _backup(self, run_id: str, path: Path) -> str | None:
        if not path.exists():
            return None
        dest = self.state / "backups" / run_id / (str(path).strip("/").replace("/", "__"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        return str(dest)

    def apply(self, plan: Plan, auth: Authorization) -> Outcome:
        if plan.empty:
            return Outcome(None, [], "nothing-to-do")
        if not auth.granted(plan):
            return Outcome(None, [], "declined")
        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        applied: list[dict[str, Any]] = []
        self._journal({"run_id": run_id, "event": "start", "plan": plan.plan_id, "title": plan.title, "at": dt.datetime.now(dt.timezone.utc).isoformat()})
        try:
            for m in plan.mutations:
                record = self._apply_one(run_id, m)
                applied.append(record)
                self._journal({"run_id": run_id, "event": "applied", **record})
        except Exception as exc:  # partial application is recorded, never hidden
            self._journal({"run_id": run_id, "event": "failed", "error": str(exc)})
            return Outcome(run_id, applied, "failed", str(exc))
        self._journal({"run_id": run_id, "event": "done"})
        return Outcome(run_id, applied, "applied")

    def _apply_one(self, run_id: str, m: Mutation) -> dict[str, Any]:
        path = Path(m.target)
        if m.kind == "chmod":
            before = stat.S_IMODE(path.stat().st_mode)
            os.chmod(path, int(m.detail["mode"], 8))
            return {"kind": "chmod", "target": m.target, "before": oct(before), "after": m.detail["mode"]}
        if m.kind == "managed_block":
            existing = path.read_text() if path.exists() else ""
            backup = self._backup(run_id, path)
            new = managed_text(existing, m.detail["name"], m.detail["body"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new)
            return {
                "kind": "managed_block",
                "target": m.target,
                "name": m.detail["name"],
                "backup": backup,
                "created": backup is None,
                "before_sha256": hashlib.sha256(existing.encode()).hexdigest() if existing else None,
                "after_sha256": hashlib.sha256(new.encode()).hexdigest(),
            }
        if m.kind == "mkdir":
            existed = path.exists()
            path.mkdir(parents=True, exist_ok=True)
            return {"kind": "mkdir", "target": m.target, "created": not existed}
        if m.kind == "run":
            result = self.runner(list(m.detail["argv"]))
            if not result.ok:
                raise RuntimeError(f"{' '.join(m.detail['argv'])}: {result.error or result.stderr.strip()[:300] or f'exit {result.returncode}'}")
            return {"kind": "run", "target": m.target, "argv": m.detail["argv"], "undo": m.detail.get("undo")}
        raise ValueError(f"unknown mutation kind {m.kind}")

    # rollback ------------------------------------------------------------------------------------------------

    def journal(self) -> list[dict[str, Any]]:
        path = self.state / "journal.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def rollback_plan(self, run_id: str) -> Plan:
        entries = [e for e in self.journal() if e.get("run_id") == run_id and e.get("event") == "applied"]
        if not entries:
            raise LookupError(f"no applied changes recorded for run {run_id}")
        plan = Plan(f"rollback:{run_id}", f"Roll back {run_id}")
        for e in reversed(entries):
            if e["kind"] == "chmod":
                plan.mutations.append(
                    Mutation("chmod", e["target"], {"mode": e["before"][2:].rjust(4, "0")}, True, f"restore mode {e['before']} on {e['target']}")
                )
            elif e["kind"] == "managed_block":
                plan.mutations.append(
                    Mutation(
                        "restore_file",
                        e["target"],
                        {"backup": e["backup"], "name": e["name"], "created": e["created"]},
                        True,
                        f"restore {e['target']} from backup" if e["backup"] else f"remove the jadis block from {e['target']}",
                    )
                )
            elif e["kind"] == "run" and e.get("undo"):
                plan.mutations.append(Mutation("run", e["target"], {"argv": e["undo"]}, False, "undo: " + " ".join(e["undo"])))
            elif e["kind"] == "run":
                plan.notes.append(f"not reversible automatically: {' '.join(e['argv'])}")
            elif e["kind"] == "mkdir" and e.get("created"):
                plan.notes.append(f"directory {e['target']} was created; remove it by hand if no longer wanted")
        return plan

    def apply_rollback(self, plan: Plan, auth: Authorization) -> Outcome:
        restorers = [m for m in plan.mutations if m.kind == "restore_file"]
        others = Plan(plan.plan_id, plan.title, [m for m in plan.mutations if m.kind != "restore_file"], plan.notes)
        if plan.empty:
            return Outcome(None, [], "nothing-to-do")
        if not auth.granted(plan):
            return Outcome(None, [], "declined")
        done = []
        for m in restorers:
            path = Path(m.target)
            if m.detail["backup"]:
                shutil.copy2(m.detail["backup"], path)
            elif path.exists():
                path.write_text(remove_managed(path.read_text(), m.detail["name"]))
            done.append({"kind": "restore_file", "target": m.target})
        outcome = self.apply(others, Authorization(yes=True)) if not others.empty else Outcome(None, [], "applied")
        return Outcome(outcome.run_id, done + outcome.applied, outcome.status if others.mutations else "applied", outcome.error)
