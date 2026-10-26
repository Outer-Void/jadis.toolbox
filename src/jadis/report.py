"""Can I reproduce this environment later? Snapshots and diffs.

A snapshot is the environment fingerprint plus doctor results for a profile. It never contains environment
values, key material or tokens: it passes through the same redactor as every other output. Snapshots can be
written to `.jadis/environment.json` and compared with `jadis env diff`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from jadis import __version__, doctor
from jadis.inspect import Inspection
from jadis.profiles import Profile


def snapshot(i: Inspection, profile: Profile) -> dict[str, Any]:
    results = doctor.run(i, profile)
    return {
        "format": "jadis-snapshot v1",
        "jadis_version": __version__,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "profile": profile.name,
        "environment": i.fingerprint(),
        "doctor": {"summary": doctor.summary(results), "checks": [r.to_dict() for r in results]},
    }


VOLATILE = ("generated_at", "memory", "disk", "network")


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(data, list) and all(not isinstance(x, (dict, list)) for x in data):
        out[prefix] = sorted(map(str, data))
    elif isinstance(data, list):
        for n, v in enumerate(data):
            key = v.get("check_id") if isinstance(v, dict) and "check_id" in v else str(n)
            out.update(flatten(v, f"{prefix}[{key}]"))
    else:
        out[prefix] = data
    return out


def diff(old: dict[str, Any], new: dict[str, Any], include_volatile: bool = False) -> list[dict[str, Any]]:
    a, b = flatten(old), flatten(new)
    changes = []
    for key in sorted(set(a) | set(b)):
        if not include_volatile and any(part in key.split(".") or key.endswith(part) for part in VOLATILE):
            continue
        if a.get(key, "<absent>") != b.get(key, "<absent>"):
            changes.append({"key": key, "old": a.get(key, "<absent>"), "new": b.get(key, "<absent>")})
    return changes
