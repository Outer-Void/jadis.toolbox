"""Declarative toolchain profiles (`jadis/profiles/*.json`).

A profile names required and optional tools (with optional minimum versions), the doctor checks it needs,
the environments it supports, per-environment package mappings and notes. `extends` composes profiles.
`validate` rejects unknown keys, tools jadis cannot probe, unknown checks, bad versions and package names.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

KEYS = {"profile", "summary", "extends", "environments", "requires", "optional", "checks", "packages", "notes"}
KINDS = {"termux", "proot-debian", "debian", "debian-family", "proot-other", "linux-other"}
FAMILIES = {"termux", "apt"}
VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")


class ProfileError(ValueError):
    pass


@dataclass
class Requirement:
    tool: str
    minimum: str | None
    required: bool
    origin: str


@dataclass
class Profile:
    name: str
    summary: str
    environments: list[str]
    requirements: list[Requirement] = field(default_factory=list)
    checks: list[tuple[str, str, list[str]]] = field(default_factory=list)  # (check_id, from profile, envs)
    packages: dict[str, dict[str, str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)

    def package(self, family: str, tool: str) -> str | None:
        return self.packages.get(family, {}).get(tool)


def raw_profiles() -> dict[str, dict[str, Any]]:
    base = resources.files("jadis") / "profiles"
    return {entry.name[:-5]: json.loads(entry.read_text("utf-8")) for entry in base.iterdir() if entry.name.endswith(".json")}


def validate(raw: dict[str, dict[str, Any]], tools: set[str], checks: set[str]) -> list[str]:
    problems = []
    for name, data in raw.items():
        where = f"profile {name}"
        if data.get("profile") != name:
            problems.append(f"{where}: 'profile' must equal the file name")
        if set(data) - KEYS:
            problems.append(f"{where}: unknown keys {sorted(set(data) - KEYS)}")
        for parent in data.get("extends", []):
            if parent not in raw:
                problems.append(f"{where}: extends unknown profile {parent}")
        for kind in data.get("environments", []):
            if kind not in KINDS:
                problems.append(f"{where}: unknown environment {kind}")
        for section in ("requires", "optional"):
            for item in data.get(section, []):
                if item.get("tool") not in tools:
                    problems.append(f"{where}: {section} names unknown tool {item.get('tool')!r}")
                if "min" in item and not VERSION_RE.match(str(item["min"])):
                    problems.append(f"{where}: bad minimum version {item['min']!r}")
                if set(item) - {"tool", "min"}:
                    problems.append(f"{where}: unknown requirement keys {sorted(set(item) - {'tool', 'min'})}")
        for check in data.get("checks", []):
            if check not in checks:
                problems.append(f"{where}: unknown check {check}")
        for family, mapping in data.get("packages", {}).items():
            if family not in FAMILIES:
                problems.append(f"{where}: unknown package family {family}")
            for tool, package in mapping.items():
                if tool not in tools or not PACKAGE_RE.match(package):
                    problems.append(f"{where}: bad package mapping {tool!r} -> {package!r}")
    for name in raw:
        cycle = _cycle(raw, name, [])
        if cycle:
            problems.append(f"profile {name}: extends cycle through {cycle}")
    return problems


def _cycle(raw: dict[str, dict[str, Any]], n: str, path: list[str]) -> str | None:
    if n in path:
        return n
    for parent in raw.get(n, {}).get("extends", []):
        found = _cycle(raw, parent, [*path, n])
        if found:
            return found
    return None


def resolve(name: str, raw: dict[str, dict[str, Any]] | None = None) -> Profile:
    raw = raw if raw is not None else raw_profiles()
    if name not in raw:
        raise ProfileError(f"unknown profile {name!r} (known: {', '.join(sorted(raw))})")
    top = raw[name]
    profile = Profile(name, top.get("summary", ""), list(top.get("environments", [])))
    order: list[str] = []

    def visit(n: str) -> None:
        for parent in raw[n].get("extends", []):
            visit(parent)
        if n not in order:
            order.append(n)

    visit(name)
    profile.chain = order
    reqs: dict[str, Requirement] = {}
    for n in order:
        data = raw[n]
        envs = list(data.get("environments", []))
        for section, required in (("requires", True), ("optional", False)):
            for item in data.get(section, []):
                tool, minimum = item["tool"], item.get("min")
                prev = reqs.get(tool)
                if prev is None or (required and not prev.required):
                    reqs[tool] = Requirement(tool, minimum or (prev.minimum if prev else None), required, n)
                elif minimum and (prev.minimum is None or version_tuple(minimum) > version_tuple(prev.minimum)):
                    prev.minimum = minimum
        for check in data.get("checks", []):
            if check not in [c[0] for c in profile.checks]:
                profile.checks.append((check, n, envs))
        for family, mapping in data.get("packages", {}).items():
            profile.packages.setdefault(family, {}).update(mapping)
        profile.notes.extend(note for note in data.get("notes", []) if note not in profile.notes)
    profile.requirements = sorted(reqs.values(), key=lambda r: (not r.required, r.tool))
    return profile


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", value)[:4])


def satisfies(found: str, minimum: str) -> bool | None:
    """None when the found version cannot be compared."""
    if not re.match(r"^\d", found or ""):
        return None
    return version_tuple(found) >= version_tuple(minimum)
