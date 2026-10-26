"""One read-only inspection of the machine, computed lazily and shared by every command in one invocation."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from jadis import environment as envmod
from jadis import probes
from jadis.system import System


class Inspection:
    def __init__(self, system: System, cwd: str = "."):
        self.system = system
        self.cwd = cwd
        self._tools: dict[str, dict[str, Any]] = {}

    @cached_property
    def signals(self) -> envmod.Signals:
        return envmod.detect_signals(self.system)

    @cached_property
    def classification(self) -> envmod.Classification:
        return envmod.classify(self.signals)

    @property
    def kind(self) -> str:
        return self.classification.kind

    @cached_property
    def home(self) -> str:
        return self.system.env.get("HOME", "")

    @cached_property
    def path_entries(self) -> list[str]:
        return [p for p in self.system.env.get("PATH", "").split(":") if p]

    def tools(self, names: set[str] | None = None) -> dict[str, dict[str, Any]]:
        wanted = {t.name for t in probes.TOOLS} if names is None else set(names)
        missing = wanted - set(self._tools)
        if missing:
            self._tools.update(probes.probe_tools(self.system, missing))
        return {n: self._tools[n] for n in sorted(wanted) if n in self._tools}

    @cached_property
    def android_sdk(self) -> dict[str, Any]:
        return probes.android_sdk(self.system, self.signals.architecture)

    @cached_property
    def java_home(self) -> dict[str, Any]:
        return probes.java_home(self.system)

    @cached_property
    def vulkan(self) -> dict[str, Any]:
        return probes.vulkan(self.system)

    def fingerprint(self, include_tools: bool = True) -> dict[str, Any]:
        s, c = self.signals, self.classification
        osr = s.os_release
        data: dict[str, Any] = {
            "format": "jadis-environment v1",
            "classification": c.to_dict(),
            "platform": "android" if s.android else ("linux" if osr or s.kernel != envmod.UNKNOWN else envmod.UNKNOWN),
            "android": s.android,
            "termux": c.kind == "termux",
            "termux_visible": s.termux_installed,
            "proot": s.proot,
            "ci": s.ci,
            "container": s.container,
            "distribution": osr.get("ID", envmod.UNKNOWN),
            "distribution_version": osr.get("VERSION_ID", envmod.UNKNOWN),
            "distribution_codename": osr.get("VERSION_CODENAME", envmod.UNKNOWN),
            "architecture": s.architecture,
            "kernel": s.kernel,
            "libc": envmod.detect_libc(self.system, c.kind),
            "identity": envmod.identity(self.system),
            "shell": envmod.shell(self.system),
            "package_manager": envmod.package_manager(self.system, c.kind),
            "memory": envmod.memory(self.system),
            "disk": envmod.disk(self.system, self.home or "/"),
            "storage": envmod.storage(self.system, c.kind, self.home),
            "network": envmod.network(self.system),
        }
        if include_tools:
            data["tools"] = self.tools()
            data["android_sdk"] = self.android_sdk
            data["java_home"] = self.java_home
            data["vulkan"] = self.vulkan
        return data
