"""Optional BLUX subprocess provider (BLUX ADR-0009): `jadis blux-capability ID`, request JSON on stdin.

Only read-only capabilities exist here: environment.inspect, environment.doctor, environment.snapshot and
toolchain.inspect. They run the same engine as the CLI. Repair, bootstrap, venv and restore have no BLUX
capability at all, so BLUX cannot reach a mutation. Those stay behind jadis's own authorization. BLUX is
never required: without it, nothing in jadis changes.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from jadis import doctor, report
from jadis.model import ExitCode
from jadis.profiles import ProfileError, resolve

if TYPE_CHECKING:
    from jadis.cli import Context, Result

READ_ONLY = ("environment.inspect", "environment.doctor", "environment.snapshot", "toolchain.inspect")


def error(code: str, message: str) -> Result:
    return ExitCode.VERIFICATION_FAILED, {"error": {"code": code, "message": message, "details": {}}}, [message]


def handle(ctx: Context, capability_id: str) -> Result:
    if capability_id not in READ_ONLY:
        return error("UNSUPPORTED_CAPABILITY", f"{capability_id} is not a jadis BLUX capability (read-only capabilities only: {', '.join(READ_ONLY)})")
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return error("MALFORMED_REQUEST", "request on stdin is not JSON")
    params: dict[str, Any] = request.get("input", {}) if isinstance(request, dict) else {}
    try:
        if capability_id == "environment.inspect":
            out = ctx.inspection.fingerprint(include_tools=False)
        elif capability_id == "toolchain.inspect":
            out = {"tools": ctx.inspection.tools(), "android_sdk": ctx.inspection.android_sdk, "java_home": ctx.inspection.java_home}
        elif capability_id == "environment.doctor":
            profile = resolve(str(params.get("profile", "minimal")))
            results = doctor.run(ctx.inspection, profile)
            out = {"profile": profile.name, "environment": ctx.inspection.kind, "summary": doctor.summary(results), "checks": [r.to_dict() for r in results]}
        else:
            out = report.snapshot(ctx.inspection, resolve(str(params.get("profile", "outer-void"))))
    except ProfileError as exc:
        return error("BAD_INPUT", str(exc))
    return ExitCode.OK, out, []
