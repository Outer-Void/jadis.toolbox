"""What's broken? What am I missing? The doctor engine.

Checks only *read* the inspection: the doctor has no mutation API at all. Every PASS carries evidence (the
`Check` model rejects a PASS without it). Network-dependent checks are marked `network: true`, and being offline
never turns a healthy local environment into a FAIL.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

from jadis import environment as envmod
from jadis.environment import TERMUX_ROOT
from jadis.inspect import Inspection
from jadis.model import UNKNOWN, Check, Severity, Status
from jadis.profiles import Profile, satisfies

CheckFn = Callable[[Inspection], list[Check]]
REGISTRY: dict[str, CheckFn] = {}


def check(check_id: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        REGISTRY[check_id] = fn
        return fn

    return register


def C(check_id: str, category: str, status: Status, severity: Severity, summary: str, **kw: Any) -> Check:
    return Check(check_id, category, status, severity, summary, **kw)


P, W, F, S, U = Status.PASS, Status.WARN, Status.FAIL, Status.SKIP, Status.UNKNOWN
INFO, LOW, MED, HIGH = Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH


# environment -------------------------------------------------------------------------------------------------


@check("env.classified")
def env_classified(i: Inspection) -> list[Check]:
    c = i.classification
    if c.kind == UNKNOWN:
        return [
            C(
                "env.classified",
                "environment",
                U,
                HIGH,
                "Environment could not be classified",
                detected=c.to_dict(),
                evidence=c.reasons,
                suggested_fix="Run `jadis env --json` and report the ambiguities; jadis will not guess.",
            )
        ]
    return [C("env.classified", "environment", P, INFO, f"Environment: {c.kind} ({c.confidence} confidence)", detected=c.kind, evidence=c.reasons)]


@check("env.supported")
def env_supported(i: Inspection) -> list[Check]:
    kind = i.kind
    supported = {"termux": "first-class", "proot-debian": "first-class", "debian": "first-class", "debian-family": "degraded"}
    if kind in supported:
        return [
            C(
                "env.supported",
                "environment",
                P if supported[kind] == "first-class" else W,
                INFO if supported[kind] == "first-class" else LOW,
                f"{kind}: {supported[kind]} support",
                detected=kind,
                evidence=[f"classified as {kind}"],
            )
        ]
    return [C("env.supported", "environment", W, MED, f"{kind}: unsupported; diagnostics only", detected=kind)]


# PATH and shell ------------------------------------------------------------------------------------------------


@check("path.duplicates")
def path_duplicates(i: Inspection) -> list[Check]:
    seen: set[str] = set()
    dupes = sorted({p for p in i.path_entries if p in seen or seen.add(p)})  # type: ignore[func-returns-value]
    if dupes:
        return [
            C(
                "path.duplicates",
                "shell",
                W,
                LOW,
                f"{len(dupes)} duplicate PATH entr{'y' if len(dupes) == 1 else 'ies'}",
                detected=dupes,
                suggested_fix="Remove the repeated export from your shell startup files (jadis shows where; see `jadis shell doctor`).",
            )
        ]
    return [C("path.duplicates", "shell", P, INFO, "No duplicate PATH entries", evidence=[f"{len(i.path_entries)} PATH entries, all unique"])]


@check("path.dead")
def path_dead(i: Inspection) -> list[Check]:
    dead = [p for p in i.path_entries if not i.system.is_dir(p)]
    if dead:
        return [C("path.dead", "shell", W, LOW, f"{len(dead)} PATH entr{'y does' if len(dead) == 1 else 'ies do'} not exist", detected=dead)]
    return [C("path.dead", "shell", P, INFO, "Every PATH entry exists", evidence=[f"{len(i.path_entries)} directories checked"])]


@check("path.termux-leak")
def path_termux_leak(i: Inspection) -> list[Check]:
    if i.kind not in ("proot-debian", "proot-other"):
        return [C("path.termux-leak", "proot", S, INFO, "Not a PRoot guest")]
    leaked = [p for p in i.path_entries if p.startswith(TERMUX_ROOT)]
    pkg = i.system.which("pkg")
    out = []
    if leaked:
        out.append(
            C(
                "path.termux-leak",
                "proot",
                W,
                MED,
                f"Termux directories are on the guest PATH: {', '.join(leaked)}",
                detected=leaked,
                suggested_fix="Termux (Bionic) binaries run inside the guest but bypass its package manager and libc; keep them out of PATH or put them after the guest's directories deliberately.",
            )
        )
    if pkg and pkg.startswith(TERMUX_ROOT):
        out.append(
            C(
                "path.termux-pkg",
                "proot",
                W,
                HIGH,
                "Termux's `pkg` is callable from the Debian guest",
                detected=pkg,
                suggested_fix="Use apt-get inside the guest. Running pkg here changes the Termux host, not this Debian.",
            )
        )
    return out or [C("path.termux-leak", "proot", P, INFO, "No Termux directories on the guest PATH", evidence=[f"{len(i.path_entries)} PATH entries checked"])]


STARTUP_FILES = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile", ".zshenv", ".zshrc.local")
ALIAS_RE = re.compile(r"^\s*alias\s+([A-Za-z0-9_.-]+)=", re.M)
FUNC_RE = re.compile(r"^\s*(?:function\s+)?([A-Za-z0-9_.-]+)\s*\(\)\s*\{", re.M)
CORE_NAMES = {"grep", "sed", "find", "ls", "cat", "rm", "cp", "mv", "cd", "python", "python3", "pip", "git", "diff", "make", "ssh"}


@check("shell.startup-files")
def shell_startup(i: Inspection) -> list[Check]:
    present = [f for f in STARTUP_FILES if i.system.exists(f"{i.home}/{f}")]
    return [
        C(
            "shell.startup-files",
            "shell",
            P,
            INFO,
            f"Startup files: {', '.join(present) or 'none'}",
            detected=present,
            evidence=[f"checked {', '.join(STARTUP_FILES)} under ~"],
        )
    ]


@check("shell.shadows")
def shell_shadows(i: Inspection) -> list[Check]:
    out = []
    tools = i.tools({"grep", "sed", "find"})
    for name, t in tools.items():
        if t.get("shadowed_by"):
            out.append(
                C(
                    "shell.shadow-binary",
                    "shell",
                    W,
                    MED,
                    f"`{name}` is really `{t['shadowed_by']}`",
                    detected=t.get("resolves_to"),
                    expected=name,
                    suggested_fix=f"Scripts that rely on GNU {name} options may misbehave; call the real binary by path or fix the link.",
                )
            )
    for f in STARTUP_FILES:
        text = i.system.read_text(f"{i.home}/{f}")
        if not text:
            continue
        for kind, rx in (("alias", ALIAS_RE), ("function", FUNC_RE)):
            for name in sorted({m.group(1) for m in rx.finditer(text)} & CORE_NAMES):
                out.append(
                    C(
                        "shell.shadow-definition",
                        "shell",
                        W,
                        LOW,
                        f"{f} defines {kind} `{name}`, shadowing the command",
                        detected={"file": f, kind: name},
                        suggested_fix="Interactive aliases are fine; non-interactive scripts never see them. Rename it if it changes behavior.",
                    )
                )
    return out or [
        C(
            "shell.shadows",
            "shell",
            P,
            INFO,
            "No shadowed core commands",
            evidence=["grep/sed/find resolve to themselves; no aliases or functions shadow core commands"],
        )
    ]


# resources -----------------------------------------------------------------------------------------------------


@check("disk.free")
def disk_free(i: Inspection) -> list[Check]:
    usage = i.system.disk_free(i.home or "/")
    if not usage:
        return [C("disk.free", "resources", U, LOW, "Free disk space unknown")]
    free_mib = usage[0] // 2**20
    if free_mib < 512:
        return [C("disk.free", "resources", F, HIGH, f"Only {free_mib} MiB free in ~", detected=free_mib, expected=">= 2048 MiB")]
    if free_mib < 2048:
        return [C("disk.free", "resources", W, MED, f"{free_mib} MiB free in ~ (builds need more)", detected=free_mib, expected=">= 2048 MiB")]
    return [C("disk.free", "resources", P, INFO, f"{free_mib} MiB free in ~", detected=free_mib, evidence=["statvfs of the home directory"])]


@check("network.local")
def network_local(i: Inspection) -> list[Check]:
    routes = i.system.read_text("/proc/net/route")
    if routes is None:
        return [C("network.local", "network", U, INFO, "Route table unreadable; network state unknown (nothing local depends on it)", network=True)]
    default = any(line.split()[1:2] == ["00000000"] for line in routes.splitlines()[1:] if line.split())
    if default:
        return [C("network.local", "network", P, INFO, "A default route exists (no remote host was contacted)", evidence=["/proc/net/route"], network=True)]
    return [C("network.local", "network", W, INFO, "No default route: offline. Local diagnostics are unaffected", network=True)]


# git / ssh -----------------------------------------------------------------------------------------------------


def git_config(i: Inspection, key: str) -> str | None:
    result = i.system.run(["git", "config", "--global", "--get", key], timeout=5)
    return (result.stdout.strip() or None) if result.ok else None


@check("git.identity")
def git_identity(i: Inspection) -> list[Check]:
    if not i.system.which("git"):
        return [C("git.identity", "git", S, INFO, "git is not installed")]
    name, email = git_config(i, "user.name"), git_config(i, "user.email")
    if name and email:
        return [
            C(
                "git.identity",
                "git",
                P,
                INFO,
                "Global git identity is configured",
                detected={"user.name": "set", "user.email": "set"},
                evidence=["git config --global user.name/user.email"],
            )
        ]
    missing = [k for k, v in (("user.name", name), ("user.email", email)) if not v]
    return [
        C(
            "git.identity",
            "git",
            W,
            MED,
            f"Global git identity incomplete: {', '.join(missing)} unset (repository-level config may still set it)",
            detected=missing,
            suggested_fix='git config --global user.name "..." and user.email "..." (jadis never sets your identity)',
        )
    ]


@check("git.default-branch")
def git_default_branch(i: Inspection) -> list[Check]:
    if not i.system.which("git"):
        return [C("git.default-branch", "git", S, INFO, "git is not installed")]
    value = git_config(i, "init.defaultBranch")
    if value:
        return [C("git.default-branch", "git", P, INFO, f"init.defaultBranch = {value}", detected=value, evidence=["git config --global init.defaultBranch"])]
    return [
        C(
            "git.default-branch",
            "git",
            W,
            LOW,
            "init.defaultBranch is unset (git warns on every init)",
            expected="main",
            suggested_fix="jadis repair git-default-branch",
            auto_fixable=True,
        )
    ]


def private_keys(i: Inspection) -> list[str]:
    names = i.system.listdir(f"{i.home}/.ssh") or []
    return [n for n in names if n.startswith("id_") and not n.endswith(".pub") and "-cert" not in n]


@check("ssh.dir-permissions")
def ssh_permissions(i: Inspection) -> list[Check]:
    ssh = f"{i.home}/.ssh"
    if not i.system.is_dir(ssh):
        return [C("ssh.dir-permissions", "ssh", S, INFO, "~/.ssh does not exist")]
    out = []
    mode = i.system.mode(ssh)
    if mode is not None and mode & 0o077:
        out.append(
            C(
                "ssh.dir-permissions",
                "ssh",
                F,
                HIGH,
                f"~/.ssh is mode {mode:o} (others can access it)",
                detected=oct(mode),
                expected="0o700",
                suggested_fix="jadis repair ssh-permissions",
                auto_fixable=True,
            )
        )
    for key in private_keys(i):
        km = i.system.mode(f"{ssh}/{key}")
        if km is not None and km & 0o077:
            out.append(
                C(
                    "ssh.key-permissions",
                    "ssh",
                    F,
                    HIGH,
                    f"Private key ~/.ssh/{key} is mode {km:o}",
                    detected=oct(km),
                    expected="0o600",
                    suggested_fix="jadis repair ssh-permissions",
                    auto_fixable=True,
                )
            )
    return out or [
        C(
            "ssh.dir-permissions",
            "ssh",
            P,
            INFO,
            f"~/.ssh and {len(private_keys(i))} private key(s) are private",
            evidence=["file modes only; key contents are never read"],
        )
    ]


@check("ssh.agent")
def ssh_agent(i: Inspection) -> list[Check]:
    sock = i.system.env.get("SSH_AUTH_SOCK")
    if sock and i.system.exists(sock):
        return [C("ssh.agent", "ssh", P, INFO, "An SSH agent socket is available", evidence=["$SSH_AUTH_SOCK points to an existing socket"])]
    return [C("ssh.agent", "ssh", W, INFO, "No SSH agent in this shell", suggested_fix='eval "$(ssh-agent -s)" && ssh-add')]


# python --------------------------------------------------------------------------------------------------------


@check("python.venv-module")
def python_venv(i: Inspection) -> list[Check]:
    if not i.system.which("python3"):
        return [C("python.venv-module", "python", S, INFO, "python3 is not installed")]
    result = i.system.run(["python3", "-c", "import venv, ensurepip"], timeout=10)
    if result.ok:
        return [C("python.venv-module", "python", P, INFO, "venv and ensurepip are available", evidence=["python3 -c 'import venv, ensurepip'"])]
    fix = "pkg install python" if i.kind == "termux" else "sudo apt-get install python3-venv"
    return [
        C(
            "python.venv-module",
            "python",
            F,
            HIGH,
            "python3 cannot create virtual environments",
            detected=(result.error or result.stderr.strip())[:200],
            suggested_fix=fix,
        )
    ]


@check("python.externally-managed")
def python_externally_managed(i: Inspection) -> list[Check]:
    if not i.system.which("python3"):
        return [C("python.externally-managed", "python", S, INFO, "python3 is not installed")]
    result = i.system.run(
        ["python3", "-c", "import sysconfig, os; print(os.path.exists(os.path.join(sysconfig.get_path('stdlib'), 'EXTERNALLY-MANAGED')))"], timeout=10
    )
    if not result.ok:
        return [C("python.externally-managed", "python", U, INFO, "Could not determine whether Python is externally managed")]
    managed = result.stdout.strip() == "True"
    return [
        C(
            "python.externally-managed",
            "python",
            P,
            INFO,
            "System Python is externally managed (PEP 668): use a venv for project packages" if managed else "System Python is not marked externally managed",
            detected=managed,
            evidence=["EXTERNALLY-MANAGED marker in the stdlib directory"],
        )
    ]


@check("python.project-venv")
def python_project_venv(i: Inspection) -> list[Check]:
    markers = [m for m in ("pyproject.toml", "requirements.txt", "setup.py") if i.system.exists(os.path.join(i.cwd, m))]
    if not markers:
        return [C("python.project-venv", "python", S, INFO, "No Python project in the current directory")]
    venv = os.path.join(i.cwd, ".venv")
    if not i.system.exists(venv):
        return [C("python.project-venv", "python", W, LOW, "Python project without a .venv", detected=markers, suggested_fix="jadis python venv")]
    result = i.system.run([os.path.join(venv, "bin", "python"), "-c", "import sys; print(sys.prefix != sys.base_prefix)"], timeout=10)
    if result.ok and result.stdout.strip() == "True":
        return [C("python.project-venv", "python", P, INFO, ".venv works", evidence=[".venv/bin/python runs inside its own prefix"])]
    return [
        C(
            "python.project-venv",
            "python",
            F,
            MED,
            ".venv exists but is broken",
            detected=(result.error or result.stderr.strip() or result.stdout.strip())[:200],
            suggested_fix="Recreate it: jadis python venv --recreate",
        )
    ]


# node ----------------------------------------------------------------------------------------------------------

LOCKFILES = {"package-lock.json": "npm", "yarn.lock": "yarn", "pnpm-lock.yaml": "pnpm", "bun.lockb": "bun"}


@check("node.lockfiles")
def node_lockfiles(i: Inspection) -> list[Check]:
    if not i.system.exists(os.path.join(i.cwd, "package.json")):
        return [C("node.lockfiles", "node", S, INFO, "No package.json in the current directory")]
    found = {f: m for f, m in LOCKFILES.items() if i.system.exists(os.path.join(i.cwd, f))}
    if len(found) > 1:
        return [
            C(
                "node.lockfiles",
                "node",
                W,
                MED,
                f"Several lockfiles: {', '.join(found)}",
                detected=found,
                suggested_fix="Keep the lockfile of the package manager the project uses.",
            )
        ]
    if not found:
        return [C("node.lockfiles", "node", W, LOW, "No lockfile: installs are not reproducible")]
    ((f, m),) = found.items()
    return [C("node.lockfiles", "node", P, INFO, f"Package manager: {m}", detected=m, evidence=[f])]


# java / android ------------------------------------------------------------------------------------------------


@check("java.java-home")
def java_home(i: Inspection) -> list[Check]:
    jh = i.java_home
    if not jh.get("JAVA_HOME"):
        return [C("java.java-home", "java", W if i.system.which("java") else S, INFO, "JAVA_HOME is unset (Gradle falls back to `java` on PATH)")]
    if not jh.get("valid"):
        return [C("java.java-home", "java", F, HIGH, "JAVA_HOME does not contain bin/java", detected=jh["JAVA_HOME"])]
    found = i.tools({"java"}).get("java", {}).get("version")
    home_ver = i.system.run([f"{jh['JAVA_HOME']}/bin/java", "-version"], timeout=10)
    m = re.search(r'version "?(\d+)', home_ver.stdout + home_ver.stderr)
    path_major = re.match(r"(\d+)", str(found or ""))
    if m and path_major and m.group(1) != path_major.group(1):
        return [
            C(
                "java.java-home",
                "java",
                W,
                MED,
                f"JAVA_HOME is JDK {m.group(1)} but `java` on PATH is {path_major.group(1)}",
                detected={"JAVA_HOME": m.group(1), "PATH": path_major.group(1)},
            )
        ]
    return [C("java.java-home", "java", P, INFO, "JAVA_HOME is a JDK" + (f" ({m.group(1)})" if m else ""), evidence=["$JAVA_HOME/bin/java runs"])]


@check("java.gradle-wrapper")
def gradle_wrapper(i: Inspection) -> list[Check]:
    if not i.system.exists(os.path.join(i.cwd, "settings.gradle.kts")) and not i.system.exists(os.path.join(i.cwd, "settings.gradle")):
        return [C("java.gradle-wrapper", "java", S, INFO, "No Gradle project in the current directory")]
    props = i.system.read_text(os.path.join(i.cwd, "gradle/wrapper/gradle-wrapper.properties"))
    if not props or not i.system.exists(os.path.join(i.cwd, "gradlew")):
        return [C("java.gradle-wrapper", "java", W, MED, "Gradle project without a wrapper")]
    m = re.search(r"gradle-([0-9.]+)-(bin|all)\.zip", props)
    return [C("java.gradle-wrapper", "java", P, INFO, f"Gradle wrapper {m.group(1) if m else UNKNOWN}", evidence=["gradle/wrapper/gradle-wrapper.properties"])]


def defined_in(i: Inspection, names: tuple[str, ...]) -> list[str]:
    """Where shell startup files assign these variables (file:line), so a stale value can be found."""
    rx = re.compile(r"^\s*(?:export\s+)?(" + "|".join(map(re.escape, names)) + r")=", re.M)
    hits = []
    for f in STARTUP_FILES:
        text = i.system.read_text(f"{i.home}/{f}") or ""
        for m in rx.finditer(text):
            hits.append(f"~/{f}:{text.count(chr(10), 0, m.start()) + 1} ({m.group(1)})")
    return hits


@check("android.sdk")
def android_sdk(i: Inspection) -> list[Check]:
    sdk = i.android_sdk
    candidates = sdk.get("candidates") or []
    found = f" An SDK exists at {', '.join(candidates)}." if candidates else ""
    defined = defined_in(i, ("ANDROID_HOME", "ANDROID_SDK_ROOT"))
    if sdk.get("dangling"):
        return [
            C(
                "android.sdk",
                "android",
                F,
                HIGH,
                f"ANDROID_HOME/ANDROID_SDK_ROOT point to {sdk.get('ANDROID_HOME') or sdk.get('ANDROID_SDK_ROOT')}, which does not exist.{found}",
                detected={"error": sdk.get("error"), "defined_in": defined or "not in ~ startup files (inherited from the parent environment)"},
                expected="an existing SDK directory",
                suggested_fix="jadis repair android-home" if len(candidates) == 1 else "Point ANDROID_HOME at your SDK",
                auto_fixable=len(candidates) == 1,
            )
        ]
    if not sdk.get("present"):
        return [
            C(
                "android.sdk",
                "android",
                W,
                MED,
                f"No Android SDK configured ($ANDROID_HOME / $ANDROID_SDK_ROOT unset).{found}",
                suggested_fix="jadis repair android-home"
                if len(candidates) == 1
                else "Install the command-line tools and set ANDROID_HOME; Android Studio is not required.",
                auto_fixable=len(candidates) == 1,
            )
        ]
    problems = []
    if not sdk.get("platform_jars"):
        problems.append("no platforms/android-*/android.jar")
    if not sdk.get("build_tools"):
        problems.append("no build-tools")
    if problems:
        return [
            C(
                "android.sdk",
                "android",
                F,
                HIGH,
                "Android SDK incomplete: " + "; ".join(problems),
                detected={k: sdk.get(k) for k in ("platforms", "build_tools")},
            )
        ]
    return [
        C(
            "android.sdk",
            "android",
            P,
            INFO,
            f"Android SDK: platforms {', '.join(sdk['platform_jars'])}; build-tools {', '.join(sdk['build_tools'])}",
            evidence=["$ANDROID_HOME/platforms/*/android.jar", "$ANDROID_HOME/build-tools/*"],
        )
    ]


@check("android.sdk-env")
def android_sdk_env(i: Inspection) -> list[Check]:
    sdk = i.android_sdk
    if sdk.get("conflict"):
        return [
            C(
                "android.sdk-env",
                "android",
                W,
                MED,
                "ANDROID_HOME and ANDROID_SDK_ROOT point to different SDKs",
                detected={"ANDROID_HOME": sdk["ANDROID_HOME"], "ANDROID_SDK_ROOT": sdk["ANDROID_SDK_ROOT"]},
            )
        ]
    if sdk.get("ANDROID_HOME") or sdk.get("ANDROID_SDK_ROOT"):
        return [C("android.sdk-env", "android", P, INFO, "SDK environment variables agree", evidence=["ANDROID_HOME / ANDROID_SDK_ROOT compared"])]
    return [C("android.sdk-env", "android", S, INFO, "No SDK variables set")]


@check("android.build-tools-arch")
def android_build_tools_arch(i: Inspection) -> list[Check]:
    sdk = i.android_sdk
    detail = sdk.get("build_tools_detail") or {}
    if not detail:
        return [C("android.build-tools-arch", "android", S, INFO, "No build-tools to check")]
    out = []
    for version, t in sorted(detail.items()):
        if t.get("aapt2_runs_here") is False:
            override = f"{TERMUX_ROOT}/usr/bin/aapt2"
            hint = f" Termux provides a native one: -Pandroid.aapt2FromMavenOverride={override}" if i.system.exists(override) else ""
            out.append(
                C(
                    "android.build-tools-arch",
                    "android",
                    W,
                    MED,
                    f"build-tools {version} aapt2 is {t['aapt2_arch']}, this machine is {i.signals.architecture}",
                    detected=t["aapt2_arch"],
                    expected=i.signals.architecture,
                    suggested_fix="Pass a native aapt2 to Gradle." + hint + " jadis does not rewrite a valid SDK layout.",
                )
            )
    return out or [C("android.build-tools-arch", "android", P, INFO, "build-tools binaries match this architecture", evidence=["ELF header of each aapt2"])]


# termux / debian / proot ---------------------------------------------------------------------------------------


@check("termux.storage")
def termux_storage(i: Inspection) -> list[Check]:
    if i.kind != "termux":
        return [C("termux.storage", "termux", S, INFO, "Not native Termux")]
    if i.system.listdir("/storage/emulated/0") is not None:
        return [C("termux.storage", "termux", P, INFO, "Shared storage is readable", evidence=["/storage/emulated/0 listed"])]
    return [
        C(
            "termux.storage",
            "termux",
            W,
            MED,
            "No access to Android shared storage",
            suggested_fix="Run termux-setup-storage and allow the permission (needs you on the device)",
        )
    ]


@check("termux.api")
def termux_api(i: Inspection) -> list[Check]:
    if i.kind != "termux":
        return [C("termux.api", "termux", S, INFO, "Not native Termux")]
    if i.system.which("termux-battery-status"):
        return [C("termux.api", "termux", P, INFO, "termux-api commands are installed", evidence=["termux-battery-status on PATH"])]
    return [C("termux.api", "termux", W, INFO, "termux-api is not installed (optional)", suggested_fix="pkg install termux-api, plus the Termux:API app")]


@check("debian.apt")
def debian_apt(i: Inspection) -> list[Check]:
    if i.kind not in ("debian", "proot-debian", "debian-family"):
        return [C("debian.apt", "debian", S, INFO, "Not a Debian-family environment")]
    apt = i.system.which("apt-get")
    if not apt or apt.startswith(TERMUX_ROOT):
        return [C("debian.apt", "debian", F, HIGH, "No Debian apt-get in this environment", detected=apt)]
    ident = envmod.identity(i.system)
    how = "as root" if ident["root"] is True else ("via sudo" if ident["sudo"] else "not possible (no root, no sudo)")
    status = P if ident["root"] is True or ident["sudo"] else W
    return [C("debian.apt", "debian", status, INFO if status is P else MED, f"apt-get available; installs run {how}", evidence=[apt] if status is P else [])]


@check("debian.locale")
def debian_locale(i: Inspection) -> list[Check]:
    if i.kind not in ("debian", "proot-debian", "debian-family"):
        return [C("debian.locale", "debian", S, INFO, "Not a Debian-family environment")]
    env = i.system.env
    lang = env.get("LC_ALL") or env.get("LANG")
    if lang and "UTF-8" in lang.upper().replace("UTF8", "UTF-8"):
        return [C("debian.locale", "debian", P, INFO, f"UTF-8 locale ({lang})", evidence=["$LC_ALL / $LANG"])]
    return [
        C("debian.locale", "debian", W, LOW, f"Locale is {lang or 'unset'}: tools may mangle non-ASCII", suggested_fix="Set LANG=C.UTF-8 in your shell profile")
    ]


@check("proot.identity")
def proot_identity(i: Inspection) -> list[Check]:
    if i.kind not in ("proot-debian", "proot-other"):
        return [C("proot.identity", "proot", S, INFO, "Not a PRoot guest")]
    uid = i.system.uid()
    if uid == 0:
        return [
            C(
                "proot.identity",
                "proot",
                W,
                LOW,
                "Working as root inside PRoot (fake root: no real privilege, but files end up root-owned)",
                suggested_fix="proot-distro login debian --user <name>",
            )
        ]
    return [C("proot.identity", "proot", P, INFO, f"Working as uid {uid} inside PRoot", evidence=["getuid()"])]


@check("proot.limits")
def proot_limits(i: Inspection) -> list[Check]:
    if i.kind not in ("proot-debian", "proot-other"):
        return [C("proot.limits", "proot", S, INFO, "Not a PRoot guest")]
    return [
        C(
            "proot.limits",
            "proot",
            P,
            INFO,
            "PRoot limits apply: no systemd/services, no real isolation, syscall translation overhead; the Android kernel is shared",
            evidence=i.classification.reasons[:3],
        )
    ]


# gpu / llm -----------------------------------------------------------------------------------------------------


@check("vulkan.state")
def vulkan_state(i: Inspection) -> list[Check]:
    v = i.vulkan
    state = v.get("state")
    if state == "gpu":
        return [
            C(
                "vulkan.state",
                "gpu",
                P,
                INFO,
                "Vulkan GPU: " + ", ".join(d["name"] for d in v["devices"]),
                detected=v["devices"],
                evidence=["vulkaninfo --summary"],
            )
        ]
    if state == "software only":
        return [C("vulkan.state", "gpu", W, LOW, "Only a software Vulkan device (CPU)", detected=v["devices"])]
    return [
        C(
            "vulkan.state",
            "gpu",
            W,
            LOW,
            f"Vulkan: {state}",
            detected=v.get("error"),
            suggested_fix="GPU drivers are device-specific; jadis never installs them. See docs/llm-vulkan.md.",
        )
    ]


@check("llm.llama")
def llm_llama(i: Inspection) -> list[Check]:
    tools = i.tools({"llama-cli", "llama-server"})
    present = [n for n, t in tools.items() if t.get("present")]
    if present:
        return [C("llm.llama", "llm", P, INFO, "llama.cpp tools: " + ", ".join(present), evidence=[tools[n]["path"] for n in present])]
    return [
        C(
            "llm.llama",
            "llm",
            W,
            INFO,
            "llama.cpp is not on PATH",
            suggested_fix="Build it from source (see docs/llm-vulkan.md); jadis llm doctor checks the build prerequisites",
        )
    ]


# tools from profiles -------------------------------------------------------------------------------------------


def tool_checks(i: Inspection, profile: Profile) -> list[Check]:
    tools = i.tools({r.tool for r in profile.requirements})
    out = []
    for req in profile.requirements:
        t = tools.get(req.tool, {})
        cid = f"tool.{req.tool}"
        if t.get("present") is not True:
            if req.required:
                out.append(
                    C(
                        cid,
                        "tools",
                        F,
                        HIGH,
                        f"{req.tool} is missing (required by {req.origin})",
                        expected=req.minimum or "present",
                        suggested_fix=f"jadis bootstrap {profile.name} --plan",
                        auto_fixable=True,
                    )
                )
            else:
                out.append(C(cid, "tools", S, INFO, f"{req.tool}: optional, not installed"))
            continue
        version = t.get("version")
        evidence = [f"{t['path']}" + (f" -> {t['resolves_to']}" if t.get("resolves_to") else ""), f"version {version}"]
        if req.minimum:
            ok = satisfies(str(version), req.minimum)
            if ok is None:
                out.append(C(cid, "tools", U, MED, f"{req.tool} version could not be read", detected=t.get("error"), expected=f">= {req.minimum}"))
                continue
            if not ok:
                out.append(
                    C(
                        cid,
                        "tools",
                        F if req.required else W,
                        HIGH if req.required else LOW,
                        f"{req.tool} {version} is older than {req.minimum}",
                        detected=version,
                        expected=f">= {req.minimum}",
                    )
                )
                continue
        if version == UNKNOWN:
            out.append(C(cid, "tools", W, LOW, f"{req.tool} is installed but its version is unreadable", detected=t.get("error")))
            continue
        out.append(C(cid, "tools", P, INFO, f"{req.tool} {version}", detected=version, evidence=evidence))
    return out


def run(i: Inspection, profile: Profile) -> list[Check]:
    results: list[Check] = []
    for check_id, origin, envs in profile.checks:
        # Scope by environment only once the environment is known: on an unclassified machine every
        # (read-only) check runs, and environment checks always run.
        if envs and i.kind != UNKNOWN and i.kind not in envs and not check_id.startswith("env."):
            results.append(C(check_id, "profile", S, INFO, f"{check_id}: {origin} does not apply to {i.kind}"))
            continue
        try:
            results.extend(REGISTRY[check_id](i))
        except Exception as exc:  # one broken check never hides the others
            results.append(C(check_id, "internal", U, MED, f"check crashed: {exc}"))
    results.extend(tool_checks(i, profile))
    return results


def summary(results: list[Check]) -> dict[str, int]:
    counts = {s.value: 0 for s in Status}
    for r in results:
        counts[r.status.value] += 1
    return counts
