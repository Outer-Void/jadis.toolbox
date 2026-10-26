"""The only door to the machine.

Every probe reads the machine through a `System`. `RealSystem` uses the OS; `FakeSystem` serves a fixture, so
classifiers, probes and the doctor are tested against synthetic Termux, PRoot and Debian machines without
touching this one. Reading is the only thing a `System` does: writes go through `jadis.mutations`, which
plans, authorizes and journals them.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

MAX_OUTPUT = 256 * 1024


@dataclass(frozen=True)
class RunResult:
    """Outcome of one command. `error` is set when the command could not run at all."""

    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.returncode == 0


class System(Protocol):
    @property
    def env(self) -> dict[str, str]: ...

    def which(self, name: str) -> str | None: ...

    def run(self, argv: list[str], timeout: float = 10.0) -> RunResult: ...

    def read_text(self, path: str, limit: int = MAX_OUTPUT) -> str | None: ...

    def read_bytes(self, path: str, limit: int = 64) -> bytes | None: ...

    def exists(self, path: str) -> bool: ...

    def is_dir(self, path: str) -> bool: ...

    def listdir(self, path: str) -> list[str] | None: ...

    def mode(self, path: str) -> int | None: ...

    def realpath(self, path: str) -> str: ...

    def file_id(self, path: str) -> tuple[int, int] | None: ...

    def access(self, path: str, mode: int) -> bool: ...

    def disk_free(self, path: str) -> tuple[int, int] | None: ...

    def uid(self) -> int | None: ...


class RealSystem:
    """The live machine. Commands run as argv (never a shell), with a timeout and bounded output."""

    @property
    def env(self) -> dict[str, str]:
        return dict(os.environ)

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(self, argv: list[str], timeout: float = 10.0) -> RunResult:
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            return RunResult(None, error="not found")
        except PermissionError:
            return RunResult(None, error="permission denied")
        except subprocess.TimeoutExpired:
            return RunResult(None, error=f"timed out after {timeout:g}s")
        except OSError as exc:
            return RunResult(None, error=exc.strerror or str(exc))
        decode = lambda b: b[:MAX_OUTPUT].decode("utf-8", "replace")  # noqa: E731
        return RunResult(proc.returncode, decode(proc.stdout), decode(proc.stderr))

    def read_text(self, path: str, limit: int = MAX_OUTPUT) -> str | None:
        try:
            with open(path, "rb") as handle:
                return handle.read(limit).decode("utf-8", "replace")
        except OSError:
            return None

    def read_bytes(self, path: str, limit: int = 64) -> bytes | None:
        try:
            with open(path, "rb") as handle:
                return handle.read(limit)
        except OSError:
            return None

    def exists(self, path: str) -> bool:
        return os.path.lexists(path)

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def listdir(self, path: str) -> list[str] | None:
        try:
            return sorted(os.listdir(path))
        except OSError:
            return None

    def mode(self, path: str) -> int | None:
        try:
            return stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            return None

    def realpath(self, path: str) -> str:
        return os.path.realpath(path)

    def file_id(self, path: str) -> tuple[int, int] | None:
        """(device, inode): the same directory seen through a PRoot bind mount has one id."""
        try:
            st = os.stat(path)
        except OSError:
            return None
        return st.st_dev, st.st_ino

    def access(self, path: str, mode: int) -> bool:
        return os.access(path, mode)

    def disk_free(self, path: str) -> tuple[int, int] | None:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return None
        return usage.free, usage.total

    def uid(self) -> int | None:
        return os.getuid() if hasattr(os, "getuid") else None


@dataclass
class FakeSystem:
    """A machine described by data, for tests and fixtures.

    `commands` maps a space-joined argv to {"rc", "stdout", "stderr"} or {"error"}. `files` maps paths to
    contents (None marks a directory). `modes` maps paths to permission bits. `executables` maps command names
    to paths; a name absent from it is not installed.
    """

    environ: dict[str, str] = field(default_factory=dict)
    executables: dict[str, str] = field(default_factory=dict)
    commands: dict[str, dict] = field(default_factory=dict)
    files: dict[str, str | None] = field(default_factory=dict)
    modes: dict[str, int] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    unreadable: set[str] = field(default_factory=set)
    same_as: dict[str, str] = field(default_factory=dict)
    free: dict[str, list[int]] = field(default_factory=dict)
    user_id: int | None = 1000
    calls: list[list[str]] = field(default_factory=list)

    @classmethod
    def from_fixture(cls, path: str | Path) -> FakeSystem:
        data = json.loads(Path(path).read_text())
        return cls(
            environ=data.get("env", {}),
            executables=data.get("executables", {}),
            commands=data.get("commands", {}),
            files=data.get("files", {}),
            modes={k: int(v, 8) if isinstance(v, str) else v for k, v in data.get("modes", {}).items()},
            links=data.get("links", {}),
            unreadable=set(data.get("unreadable", [])),
            same_as=data.get("same_as", {}),
            free=data.get("disk", {}),
            user_id=data.get("uid", 1000),
        )

    @property
    def env(self) -> dict[str, str]:
        return dict(self.environ)

    def which(self, name: str) -> str | None:
        return self.executables.get(name)

    def run(self, argv: list[str], timeout: float = 10.0) -> RunResult:
        self.calls.append(list(argv))
        spec = self.commands.get(" ".join(argv))
        if spec is None:
            name = Path(argv[0]).name
            return RunResult(None, error="not found") if name not in self.executables else RunResult(1, "", "unsupported in fixture")
        if "error" in spec:
            return RunResult(None, error=spec["error"])
        return RunResult(spec.get("rc", 0), spec.get("stdout", ""), spec.get("stderr", ""))

    def read_text(self, path: str, limit: int = MAX_OUTPUT) -> str | None:
        if path in self.unreadable:
            return None
        content = self.files.get(path)
        return content[:limit] if isinstance(content, str) else None

    def read_bytes(self, path: str, limit: int = 64) -> bytes | None:
        """Fixture files written as "@elf:<machine>" become a minimal ELF header for that machine."""
        content = self.files.get(path)
        if path in self.unreadable or not isinstance(content, str):
            return None
        if content.startswith("@elf:"):
            machine = {"aarch64": 183, "x86_64": 62, "arm": 40, "x86": 3}[content[5:]]
            return (b"\x7fELF\x02\x01\x01" + b"\x00" * 11 + machine.to_bytes(2, "little")).ljust(limit, b"\x00")[:limit]
        return content.encode()[:limit]

    def exists(self, path: str) -> bool:
        return path in self.files or any(f.startswith(path.rstrip("/") + "/") for f in self.files)

    def is_dir(self, path: str) -> bool:
        return (path in self.files and self.files[path] is None) or any(f.startswith(path.rstrip("/") + "/") for f in self.files)

    def listdir(self, path: str) -> list[str] | None:
        if path in self.unreadable or not self.is_dir(path):
            return None
        prefix = path.rstrip("/") + "/"
        return sorted({f[len(prefix) :].split("/")[0] for f in self.files if f.startswith(prefix)})

    def mode(self, path: str) -> int | None:
        return self.modes.get(path, 0o644 if self.files.get(path) is not None and path in self.files else (0o755 if self.is_dir(path) else None))

    def realpath(self, path: str) -> str:
        return self.links.get(path, path)

    def file_id(self, path: str) -> tuple[int, int] | None:
        """Fixtures express bind mounts as `same_as`: {path: canonical path}."""
        if not self.exists(path):
            return None
        canonical = self.same_as.get(path, path)
        return 1, hash(canonical) & 0xFFFFFFFF

    def access(self, path: str, mode: int) -> bool:
        if path in self.unreadable:
            return False
        if mode & os.W_OK:
            return self.exists(path) and not path.startswith(("/system", "/proc"))
        return self.exists(path)

    def disk_free(self, path: str) -> tuple[int, int] | None:
        value = self.free.get(path)
        return (value[0], value[1]) if value else None

    def uid(self) -> int | None:
        return self.user_id
