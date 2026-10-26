"""What do I have? Toolchain probes.

Each probe is independent: a missing tool, a crashing `--version`, a timeout or unparseable output gives that
probe an `unknown`/`missing` result and never stops the others. At most two probes run at a time (the
Outer Void two-process bound). Every result says where the binary lives and where it really resolves to.
That is how JADIS sees Termux binaries leaking into a PRoot guest, or `grep` being `ugrep`.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from jadis.environment import TERMUX_ROOT
from jadis.model import UNKNOWN
from jadis.system import System

MAX_WORKERS = 2


@dataclass(frozen=True)
class ToolSpec:
    name: str
    argv: tuple[str, ...]
    pattern: str
    group: str
    expect_basename: tuple[str, ...] = ()
    timeout: float = 10.0
    stream: str = "both"


VERSION = r"(\d+(?:\.\d+)+[0-9A-Za-z.+~-]*)"
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("python3", ("python3", "--version"), r"Python " + VERSION, "python"),
    ToolSpec("pip", ("python3", "-m", "pip", "--version"), r"pip " + VERSION, "python"),
    ToolSpec("node", ("node", "--version"), r"v" + VERSION, "node"),
    ToolSpec("npm", ("npm", "--version"), VERSION, "node"),
    ToolSpec("java", ("java", "-version"), r'version "?' + VERSION, "java"),
    ToolSpec("javac", ("javac", "-version"), r"javac " + VERSION, "java"),
    ToolSpec("gradle", ("gradle", "--version"), r"Gradle " + VERSION, "java", timeout=60.0),
    ToolSpec("git", ("git", "--version"), r"git version " + VERSION, "vcs"),
    ToolSpec("ssh", ("ssh", "-V"), r"OpenSSH_([0-9][0-9A-Za-z.p]*)", "vcs"),
    ToolSpec("gh", ("gh", "--version"), r"gh version " + VERSION, "vcs"),
    ToolSpec("cmake", ("cmake", "--version"), r"cmake version " + VERSION, "build"),
    ToolSpec("make", ("make", "--version"), r"Make " + VERSION, "build"),
    ToolSpec("clang", ("clang", "--version"), r"clang version " + VERSION, "build"),
    ToolSpec("gcc", ("gcc", "--version"), r"\) " + VERSION, "build"),
    ToolSpec("adb", ("adb", "version"), r"Android Debug Bridge version " + VERSION, "android"),
    ToolSpec("fastboot", ("fastboot", "--version"), r"fastboot version " + VERSION, "android"),
    ToolSpec("jq", ("jq", "--version"), r"jq-" + VERSION, "data"),
    ToolSpec("yq", ("yq", "--version"), VERSION, "data"),
    ToolSpec("zip", ("zip", "-v"), r"Zip " + VERSION, "archive"),
    ToolSpec("unzip", ("unzip", "-v"), r"UnZip " + VERSION, "archive"),
    ToolSpec("tar", ("tar", "--version"), VERSION, "archive"),
    ToolSpec("curl", ("curl", "--version"), r"curl " + VERSION, "network"),
    ToolSpec("vulkaninfo", ("vulkaninfo", "--version"), VERSION, "gpu"),
    ToolSpec("llama-cli", ("llama-cli", "--version"), r"version: (\d+)", "llm"),
    ToolSpec("llama-server", ("llama-server", "--version"), r"version: (\d+)", "llm"),
    ToolSpec("grep", ("grep", "--version"), VERSION, "core", expect_basename=("grep",)),
    ToolSpec("sed", ("sed", "--version"), VERSION, "core", expect_basename=("sed",)),
    ToolSpec("find", ("find", "--version"), VERSION, "core", expect_basename=("find",)),
)
CORE_SHADOW_NAMES = ("grep", "sed", "find")


def origin(path: str | None) -> str:
    if not path:
        return "missing"
    if path.startswith(TERMUX_ROOT):
        return "termux"
    if path.startswith(("/usr/", "/bin/", "/sbin/")):
        return "system"
    if "/.local/" in path or "/.npm" in path or "/.cargo/" in path or "/.pyenv/" in path:
        return "user"
    return "other"


def probe_tool(system: System, spec: ToolSpec) -> dict[str, Any]:
    path = system.which(spec.argv[0])
    if not path:
        return {"name": spec.name, "group": spec.group, "present": False, "version": None, "path": None}
    real = system.realpath(path)
    result = system.run([path, *spec.argv[1:]], timeout=spec.timeout)
    data: dict[str, Any] = {
        "name": spec.name,
        "group": spec.group,
        "present": True,
        "path": path,
        "resolves_to": real if real != path else None,
        "origin": origin(real),
        "version": UNKNOWN,
    }
    if result.error:
        data["error"] = result.error
        return data
    text = result.stdout + "\n" + result.stderr
    match = re.search(spec.pattern, text)
    if match:
        data["version"] = match.group(1)
    else:
        data["error"] = "unrecognized version output"
    if spec.expect_basename:
        base = os.path.basename(real)
        if base not in spec.expect_basename:
            data["shadowed_by"] = base
    return data


def probe_tools(system: System, names: set[str] | None = None) -> dict[str, dict[str, Any]]:
    specs = [t for t in TOOLS if names is None or t.name in names]

    def one(spec: ToolSpec) -> dict[str, Any]:
        try:
            return probe_tool(system, spec)
        except Exception as exc:  # a broken probe must never stop the others
            return {"name": spec.name, "group": spec.group, "present": UNKNOWN, "version": UNKNOWN, "error": f"probe crashed: {exc}"}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(one, specs))
    return {r["name"]: r for r in results}


ELF_MACHINES = {183: "aarch64", 62: "x86_64", 40: "arm", 3: "x86"}


def elf_machine(system: System, path: str) -> str | None:
    head = system.read_bytes(path, 20)
    if not head or head[:4] != b"\x7fELF" or len(head) < 20:
        return None
    return ELF_MACHINES.get(int.from_bytes(head[18:20], "little"), "other")


def sdk_candidates(system: System) -> list[str]:
    """Standard SDK locations that look like a real SDK (platforms or build-tools present)."""
    home = system.env.get("HOME", "")
    places = [
        f"{home}/android-sdk",
        f"{home}/Android/Sdk",
        f"{home}/Android/sdk",
        "/opt/android-sdk",
        "/usr/lib/android-sdk",
        f"{TERMUX_ROOT}/home/android-sdk",
    ]
    found, seen = [], set()
    for p in dict.fromkeys(places):
        if not (system.is_dir(f"{p}/platforms") or system.is_dir(f"{p}/build-tools")):
            continue
        ident = system.file_id(p) or p
        if ident not in seen:  # PRoot binds Termux's home into the guest: one SDK, two paths
            seen.add(ident)
            found.append(p)
    return found


def android_sdk(system: System, architecture: str) -> dict[str, Any]:
    env = system.env
    home, root = env.get("ANDROID_HOME"), env.get("ANDROID_SDK_ROOT")
    sdk = home or root
    data: dict[str, Any] = {
        "ANDROID_HOME": home,
        "ANDROID_SDK_ROOT": root,
        "conflict": bool(home and root and os.path.realpath(home) != os.path.realpath(root)),
        "candidates": sdk_candidates(system),
    }
    if not sdk:
        data.update(present=False)
        return data
    if not system.is_dir(sdk):
        data.update(present=False, dangling=True, error=f"{sdk} does not exist")
        return data
    platforms = [p for p in (system.listdir(f"{sdk}/platforms") or []) if p.startswith("android-")]
    build_tools = system.listdir(f"{sdk}/build-tools") or []
    data.update(present=True, root=sdk, platforms=platforms, build_tools=build_tools)
    data["platform_jars"] = [p for p in platforms if system.exists(f"{sdk}/platforms/{p}/android.jar")]
    data["platform_tools"] = {t: system.exists(f"{sdk}/platform-tools/{t}") for t in ("adb", "fastboot")}
    tools: dict[str, Any] = {}
    for version in build_tools:
        base = f"{sdk}/build-tools/{version}"
        aapt2 = f"{base}/aapt2"
        machine = elf_machine(system, aapt2) if system.exists(aapt2) else None
        tools[version] = {
            "aapt2": system.exists(aapt2),
            "aapt2_arch": machine,
            "aapt2_runs_here": None if machine is None else machine == architecture,
            "apksigner": system.exists(f"{base}/apksigner"),
            "d8": system.exists(f"{base}/d8"),
        }
    data["build_tools_detail"] = tools
    return data


def java_home(system: System) -> dict[str, Any]:
    value = system.env.get("JAVA_HOME")
    if not value:
        return {"JAVA_HOME": None}
    return {"JAVA_HOME": value, "valid": system.exists(f"{value}/bin/java"), "has_javac": system.exists(f"{value}/bin/javac")}


def vulkan(system: System) -> dict[str, Any]:
    loaders = [
        p
        for p in (
            "/usr/lib/aarch64-linux-gnu/libvulkan.so.1",
            "/usr/lib/x86_64-linux-gnu/libvulkan.so.1",
            f"{TERMUX_ROOT}/usr/lib/libvulkan.so",
            "/system/lib64/libvulkan.so",
        )
        if system.exists(p)
    ]
    data: dict[str, Any] = {"loaders": loaders, "vulkaninfo": bool(system.which("vulkaninfo")), "devices": []}
    if not data["vulkaninfo"]:
        data["state"] = "no vulkaninfo" if loaders else "no Vulkan loader"
        return data
    result = system.run(["vulkaninfo", "--summary"], timeout=15)
    if result.error or result.returncode != 0:
        data.update(state="vulkaninfo failed", error=result.error or (result.stderr.strip()[:200] or f"exit {result.returncode}"))
        return data
    devices = re.findall(r"deviceName\s*=\s*(.+)", result.stdout)
    apis = re.findall(r"apiVersion\s*=\s*([0-9.]+)", result.stdout)
    types = re.findall(r"deviceType\s*=\s*(\S+)", result.stdout)
    data["devices"] = [
        {"name": n.strip(), "api": apis[i] if i < len(apis) else UNKNOWN, "type": types[i] if i < len(types) else UNKNOWN} for i, n in enumerate(devices)
    ]
    gpus = [d for d in data["devices"] if "CPU" not in d["type"].upper()]
    data["state"] = "gpu" if gpus else ("software only" if data["devices"] else "no devices")
    return data
