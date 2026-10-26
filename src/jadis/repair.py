"""What can safely be fixed? The repair catalogue.

Each repair inspects first and returns a `Plan` only when something needs to change, so a second run after
a successful repair plans nothing. Repairs never touch identity, keys' contents, package sources, or the
user's own lines in shell files.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from jadis.inspect import Inspection
from jadis.mutations import BEGIN, Mutation, Plan, managed_text

RepairFn = Callable[[Inspection], Plan]
REPAIRS: dict[str, tuple[str, RepairFn]] = {}


def repair(repair_id: str, summary: str) -> Callable[[RepairFn], RepairFn]:
    def register(fn: RepairFn) -> RepairFn:
        REPAIRS[repair_id] = (summary, fn)
        return fn

    return register


@repair("ssh-permissions", "Make ~/.ssh 0700 and private keys 0600 (modes only; key contents are never read)")
def ssh_permissions(i: Inspection) -> Plan:
    plan = Plan("ssh-permissions", "SSH permissions")
    ssh = f"{i.home}/.ssh"
    if not i.system.is_dir(ssh):
        return plan
    mode = i.system.mode(ssh)
    if mode is not None and mode & 0o077:
        plan.mutations.append(Mutation("chmod", ssh, {"mode": "0700"}, True, f"chmod 700 ~/.ssh (was {mode:o})"))
    for name in i.system.listdir(ssh) or []:
        if name.startswith("id_") and not name.endswith(".pub") and "-cert" not in name:
            km = i.system.mode(f"{ssh}/{name}")
            if km is not None and km & 0o077:
                plan.mutations.append(Mutation("chmod", f"{ssh}/{name}", {"mode": "0600"}, True, f"chmod 600 ~/.ssh/{name} (was {km:o})"))
    return plan


@repair("git-default-branch", "Set git's init.defaultBranch to main when it is unset")
def git_default_branch(i: Inspection) -> Plan:
    plan = Plan("git-default-branch", "Git default branch")
    if not i.system.which("git"):
        return plan
    current = i.system.run(["git", "config", "--global", "--get", "init.defaultBranch"], timeout=5)
    if current.ok and current.stdout.strip():
        return plan
    plan.mutations.append(
        Mutation(
            "run",
            "git config --global init.defaultBranch",
            {
                "argv": ["git", "config", "--global", "init.defaultBranch", "main"],
                "undo": ["git", "config", "--global", "--unset", "init.defaultBranch"],
            },
            True,
            "git config --global init.defaultBranch main",
        )
    )
    return plan


def startup_file(i: Inspection) -> str:
    shell = os.path.basename(i.system.env.get("SHELL", ""))
    return f"{i.home}/{'.zshrc' if shell == 'zsh' else '.bashrc'}"


LOCAL_BIN_BODY = '# Added by `jadis repair shell-local-bin`. Remove this block to undo.\ncase ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac\nexport PATH'


@repair("shell-local-bin", "Put ~/.local/bin on PATH through a marked block in your shell startup file")
def shell_local_bin(i: Inspection) -> Plan:
    plan = Plan("shell-local-bin", "~/.local/bin on PATH")
    local_bin = f"{i.home}/.local/bin"
    if not i.system.is_dir(local_bin) or local_bin in i.path_entries:
        return plan
    target = startup_file(i)
    existing = i.system.read_text(target) or ""
    if BEGIN.format(name="local-bin") in existing and managed_text(existing, "local-bin", LOCAL_BIN_BODY) == existing:
        plan.notes.append(f"{target} already has the block; open a new shell to pick it up")
        return plan
    plan.mutations.append(
        Mutation(
            "managed_block",
            target,
            {"name": "local-bin", "body": LOCAL_BIN_BODY},
            True,
            f"add a marked 'jadis managed: local-bin' block to {target} (backup first; your own lines are untouched)",
        )
    )
    return plan


@repair("android-home", "Export ANDROID_HOME/ANDROID_SDK_ROOT for the one SDK found, through a marked shell block")
def android_home(i: Inspection) -> Plan:
    plan = Plan("android-home", "Android SDK environment")
    sdk = i.android_sdk
    if sdk.get("present"):
        return plan
    candidates = sdk.get("candidates") or []
    if len(candidates) != 1:
        if len(candidates) > 1:
            plan.notes.append("several SDKs found (" + ", ".join(candidates) + "); choose one and set ANDROID_HOME yourself")
        return plan
    target = startup_file(i)
    path = candidates[0].replace(i.home, "$HOME", 1) if i.home and candidates[0].startswith(i.home + "/") else candidates[0]
    body = f'# Added by `jadis repair android-home`. Remove this block to undo.\nexport ANDROID_HOME="{path}"\nexport ANDROID_SDK_ROOT="$ANDROID_HOME"'
    existing = i.system.read_text(target) or ""
    if managed_text(existing, "android-home", body) == existing:
        plan.notes.append(f"{target} already sets it; open a new shell (another startup file may override it)")
        return plan
    plan.mutations.append(
        Mutation(
            "managed_block",
            target,
            {"name": "android-home", "body": body},
            True,
            f"add a marked 'jadis managed: android-home' block to {target} exporting ANDROID_HOME={path}",
        )
    )
    return plan


def plans(i: Inspection, only: list[str] | None = None) -> list[Plan]:
    chosen = only or list(REPAIRS)
    unknown = [r for r in chosen if r not in REPAIRS]
    if unknown:
        raise KeyError(", ".join(unknown))
    return [REPAIRS[r][1](i) for r in chosen]
