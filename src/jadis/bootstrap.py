"""Bootstrap plans: install what a profile needs, for this environment only.

- Detect first: tools that already work are not reinstalled.
- Package names come from the profile's mapping for this environment's family: `termux` for native Termux,
  `apt` for Debian, PRoot Debian and Debian derivatives. The two never mix. In a PRoot guest the Termux `pkg`
  that leaks onto PATH is never used, and in Termux `apt-get` is never called as Debian's.
- apt needs root or sudo. Without either the plan is refused (unsupported) rather than half-run.
- A plan is shown in full before anything runs. See `jadis.mutations` for authorization.
"""

from __future__ import annotations

from dataclasses import dataclass

from jadis.environment import TERMUX_ROOT, identity
from jadis.inspect import Inspection
from jadis.mutations import Mutation, Plan
from jadis.profiles import Profile, satisfies

FAMILY = {"termux": "termux", "proot-debian": "apt", "debian": "apt", "debian-family": "apt"}


class Unsupported(Exception):
    pass


@dataclass
class BootstrapResult:
    plan: Plan
    present: list[str]
    unavailable: list[str]


def build(i: Inspection, profile: Profile, include_optional: bool = False) -> BootstrapResult:
    family = FAMILY.get(i.kind)
    if family is None:
        raise Unsupported(f"no bootstrap for environment '{i.kind}' (supported: {', '.join(sorted(FAMILY))})")
    if profile.environments and i.kind not in profile.environments:
        raise Unsupported(f"profile {profile.name} does not apply to {i.kind}")
    wanted = [r for r in profile.requirements if r.required or include_optional]
    tools = i.tools({r.tool for r in wanted})
    present, packages, unavailable = [], [], []
    plan_notes: list[str] = []
    for req in wanted:
        t = tools.get(req.tool, {})
        # In a Debian guest a Termux binary leaking onto PATH does not count: the guest gets its own package.
        leaked = family == "apt" and t.get("origin") == "termux"
        works = t.get("present") is True and not leaked
        if leaked:
            plan_notes.append(f"{req.tool} on PATH is Termux's ({t.get('path')}); planning the guest's own package")
        if works and (not req.minimum or satisfies(str(t.get("version")), req.minimum)):
            present.append(req.tool)
            continue
        package = profile.package(family, req.tool)
        if not package:
            unavailable.append(req.tool)
        elif package not in packages:
            packages.append(package)
    plan = Plan(f"bootstrap:{profile.name}", f"Bootstrap {profile.name} on {i.kind}", notes=plan_notes)
    if unavailable:
        plan.notes.append("no package in this environment for: " + ", ".join(unavailable))
    if i.kind.startswith("proot"):
        plan.notes.append("PRoot: packages install into the guest only; services that need systemd will not start")
    if not packages:
        return BootstrapResult(plan, present, unavailable)
    if family == "termux":
        pkg = f"{TERMUX_ROOT}/usr/bin/pkg"
        if not i.system.exists(pkg):
            raise Unsupported("Termux pkg not found under the Termux prefix")
        plan.mutations.append(Mutation("run", "termux packages", {"argv": [pkg, "install", "-y", *packages]}, False, f"pkg install -y {' '.join(packages)}"))
    else:
        apt = i.system.which("apt-get")
        if not apt or apt.startswith(TERMUX_ROOT):
            raise Unsupported("this environment has no Debian apt-get")
        ident = identity(i.system)
        if ident["root"] is True:
            prefix: list[str] = []
        elif ident["sudo"]:
            prefix = [str(ident["sudo_path"])]
        else:
            raise Unsupported("apt-get needs root or sudo, and neither is available")
        plan.mutations.append(
            Mutation(
                "run",
                "apt packages",
                {"argv": [*prefix, "/usr/bin/apt-get", "install", "-y", "--no-install-recommends", *packages]},
                False,
                f"{'sudo ' if prefix else ''}apt-get install -y --no-install-recommends {' '.join(packages)}",
            )
        )
    return BootstrapResult(plan, present, unavailable)
