"""Where am I? Environment detection and classification.

Detection gathers independent signals, each with the evidence it came from. Classification then applies
explicit rules. When signals are missing or contradict each other the result is `unknown`, with the
reasons, never a guess.

Kinds: `termux` (native Termux on Android), `proot-debian` / `proot-other` (a distribution running through
PRoot, normally `proot-distro` under Termux), `debian` (native Debian), `debian-family` (Ubuntu and other
Debian derivatives, degraded support), `linux-other`, `unknown`. Whether the session is CI is a separate
flag: CI runs on any of these kinds.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from jadis.model import UNKNOWN
from jadis.system import System

TERMUX_PREFIX_RE = re.compile(r"/com\.termux/files/usr/?$")
TERMUX_ROOT = "/data/data/com.termux/files"


def parse_os_release(text: str | None) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        if re.fullmatch(r"[A-Z0-9_]+", key):
            values[key] = raw
    return values


@dataclass
class Signals:
    """Raw detection signals. Each entry in `evidence` says where a signal came from."""

    android: bool = False
    termux_prefix: bool = False
    termux_installed: bool = False
    proot_tracer: bool = False
    proot_kernel: bool = False
    proot_env: bool = False
    os_release: dict[str, str] = field(default_factory=dict)
    kernel: str = UNKNOWN
    architecture: str = UNKNOWN
    container: str | None = None
    ci: bool = False
    evidence: list[str] = field(default_factory=list)

    @property
    def proot(self) -> bool:
        return self.proot_tracer or self.proot_kernel


def detect_signals(system: System) -> Signals:
    env = system.env
    s = Signals()

    if env.get("ANDROID_ROOT") or system.exists("/system/build.prop"):
        s.android = True
        s.evidence.append("android: " + ("$ANDROID_ROOT set" if env.get("ANDROID_ROOT") else "/system/build.prop present"))
    prefix = env.get("PREFIX", "")
    if TERMUX_PREFIX_RE.search(prefix) or env.get("TERMUX_VERSION"):
        s.termux_prefix = True
        s.evidence.append("termux: " + ("$PREFIX is a Termux prefix" if TERMUX_PREFIX_RE.search(prefix) else "$TERMUX_VERSION set"))
    if system.exists(TERMUX_ROOT + "/usr/bin/pkg"):
        s.termux_installed = True
        s.evidence.append(f"termux: {TERMUX_ROOT}/usr/bin/pkg is visible")

    status = system.read_text("/proc/self/status") or ""
    match = re.search(r"^TracerPid:\s*(\d+)", status, re.M)
    if match and match.group(1) != "0":
        comm = (system.read_text(f"/proc/{match.group(1)}/comm") or "").strip()
        if comm.startswith("proot"):
            s.proot_tracer = True
            s.evidence.append(f"proot: traced by pid {match.group(1)} ({comm})")
        else:
            s.evidence.append(f"traced by pid {match.group(1)} ({comm or 'unreadable'}); not counted as PRoot")
    kernel = (system.read_text("/proc/sys/kernel/osrelease") or "").strip()
    if not kernel:  # PRoot fakes the release at the uname() syscall, not in /proc
        release = system.run(["uname", "-r"], timeout=5)
        kernel = release.stdout.strip() if release.ok else ""
    if kernel:
        s.kernel = kernel
        if "proot" in kernel.lower():
            s.proot_kernel = True
            s.evidence.append(f"proot: kernel release '{kernel}' (proot-distro default)")
    if env.get("PROOT_L2S_DIR") or env.get("PROOT_TMP_DIR"):
        s.proot_env = True
        s.evidence.append("proot: PROOT_* variables present (supporting only)")

    s.os_release = parse_os_release(system.read_text("/etc/os-release") or system.read_text("/usr/lib/os-release"))
    if s.os_release:
        s.evidence.append(f"os-release: ID={s.os_release.get('ID', '?')} VERSION_ID={s.os_release.get('VERSION_ID', '?')}")

    arch = system.run(["uname", "-m"], timeout=5)
    if arch.ok and arch.stdout.strip():
        s.architecture = arch.stdout.strip()
    elif env.get("HOSTTYPE"):
        s.architecture = env["HOSTTYPE"]

    if system.exists("/.dockerenv"):
        s.container = "docker"
    elif system.exists("/run/.containerenv"):
        s.container = "podman"
    s.ci = env.get("CI", "").lower() in ("true", "1") or env.get("GITHUB_ACTIONS") == "true"
    if s.ci:
        s.evidence.append("ci: $CI or $GITHUB_ACTIONS set")
    return s


@dataclass
class Classification:
    kind: str
    confidence: str
    reasons: list[str]
    ambiguities: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "confidence": self.confidence, "reasons": self.reasons, "ambiguities": self.ambiguities}


def classify(s: Signals) -> Classification:
    reasons = list(s.evidence)
    ambiguities: list[str] = []
    distro = s.os_release.get("ID", "").lower()
    like = s.os_release.get("ID_LIKE", "").lower().split()

    if s.proot:
        if s.termux_prefix:
            ambiguities.append("a Termux $PREFIX leaks into the PRoot guest (environment leakage, not a classification conflict)")
        if not distro:
            return Classification(UNKNOWN, "low", reasons, ambiguities + ["PRoot detected but no os-release identifies the guest"])
        kind = "proot-debian" if distro == "debian" else "proot-other"
        return Classification(kind, "high" if s.proot_tracer else "medium", reasons, ambiguities)

    if s.termux_prefix:
        if not s.android:
            return Classification(UNKNOWN, "low", reasons, ["Termux $PREFIX set but no Android signal"])
        if distro:
            ambiguities.append(f"an os-release (ID={distro}) is visible inside Termux")
        return Classification("termux", "high" if s.termux_installed else "medium", reasons, ambiguities)

    if s.android:
        return Classification(UNKNOWN, "low", reasons, ["Android signals but neither Termux nor PRoot evidence (a chroot, or an unsupported shell)"])

    if not distro:
        return Classification(UNKNOWN, "low", reasons, ["no os-release: the distribution cannot be identified"])
    if distro == "debian":
        return Classification("debian", "high", reasons, ambiguities)
    if "debian" in like:
        return Classification("debian-family", "medium", reasons, ambiguities + [f"{distro} is Debian-derived: support degrades safely"])
    return Classification("linux-other", "medium", reasons, ambiguities + [f"{distro} is not a supported family"])


def detect_libc(system: System, kind: str) -> str:
    if kind == "termux":
        return "bionic"
    result = system.run(["ldd", "--version"], timeout=5)
    text = (result.stdout + result.stderr).lower()
    if "glibc" in text or "gnu libc" in text or "gnu c library" in text:
        version = re.search(r"(\d+\.\d+)", result.stdout)
        return f"glibc {version.group(1)}" if version else "glibc"
    if "musl" in text:
        return "musl"
    return UNKNOWN


def memory(system: System) -> dict[str, Any]:
    info = system.read_text("/proc/meminfo")
    if not info:
        return {"total_mib": UNKNOWN, "available_mib": UNKNOWN}
    values = {m.group(1): int(m.group(2)) // 1024 for m in re.finditer(r"^(\w+):\s+(\d+) kB", info, re.M)}
    return {"total_mib": values.get("MemTotal", UNKNOWN), "available_mib": values.get("MemAvailable", UNKNOWN)}


def disk(system: System, path: str) -> dict[str, Any]:
    usage = system.disk_free(path)
    if not usage:
        return {"path": path, "free_mib": UNKNOWN, "total_mib": UNKNOWN}
    return {"path": path, "free_mib": usage[0] // 2**20, "total_mib": usage[1] // 2**20}


def network(system: System) -> dict[str, Any]:
    """Local evidence only; nothing is contacted. A default route means 'probably online', never 'online'."""
    routes = system.read_text("/proc/net/route")
    if routes is None:
        return {"default_route": UNKNOWN, "note": "route table unreadable (common on Android)"}
    default = any(line.split()[1:2] == ["00000000"] for line in routes.splitlines()[1:] if line.split())
    return {"default_route": default, "note": "local route table only; no network request is made"}


def storage(system: System, kind: str, home: str) -> dict[str, Any]:
    if kind not in ("termux", "proot-debian", "proot-other"):
        return {"android_shared_storage": "not applicable"}
    shared = "/storage/emulated/0"
    readable = system.listdir(shared) is not None
    data: dict[str, Any] = {"android_shared_storage": "readable" if readable else "not readable"}
    if kind == "termux":
        data["termux_storage_link"] = system.is_dir(f"{home}/storage")
        data["setup_hint"] = None if readable else "run termux-setup-storage in Termux and grant the permission"
    else:
        data["sdcard_mount"] = system.is_dir("/sdcard") or readable
    return data


def identity(system: System) -> dict[str, Any]:
    uid = system.uid()
    sudo = system.which("sudo")
    return {
        "uid": UNKNOWN if uid is None else uid,
        "root": UNKNOWN if uid is None else uid == 0,
        "sudo": bool(sudo) and uid != 0,
        "sudo_path": sudo,
    }


def shell(system: System) -> dict[str, Any]:
    env = system.env
    path = env.get("SHELL", "")
    return {"login_shell": os.path.basename(path) if path else UNKNOWN, "term": env.get("TERM", UNKNOWN)}


def package_manager(system: System, kind: str) -> dict[str, Any]:
    """The package manager that belongs to *this* environment. A Termux pkg visible from a PRoot guest is
    reported as leakage, never as the guest's package manager."""
    found: dict[str, Any] = {"native": UNKNOWN, "leaked": []}
    if kind == "termux":
        found["native"] = "pkg" if system.which("pkg") else ("apt" if system.which("apt") else UNKNOWN)
    elif kind in ("proot-debian", "debian", "debian-family"):
        found["native"] = "apt-get" if system.which("apt-get") else UNKNOWN
    pkg = system.which("pkg")
    if kind != "termux" and pkg and TERMUX_ROOT in system.realpath(pkg):
        found["leaked"].append({"name": "pkg", "path": pkg, "note": "Termux's package manager is on this environment's PATH"})
    return found
