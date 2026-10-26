"""`jadis` command line. Every command builds one result object; human and `--json` output both render it.

Exit codes (docs/cli.md): 0 ok, 1 verification failed, 2 usage, 3 unsupported environment, 4 incomplete
(declined/partial), 70 internal error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from jadis import __version__, backup, bootstrap, doctor, probes, report
from jadis import repair as repairs
from jadis.inspect import Inspection
from jadis.model import ExitCode, Status
from jadis.mutations import Authorization, Executor, Mutation, Plan
from jadis.profiles import ProfileError, raw_profiles, resolve, validate
from jadis.redact import Redactor
from jadis.system import RealSystem, System

Result = tuple[ExitCode, dict[str, Any], list[str]]
SYMBOL = {"PASS": "ok  ", "WARN": "warn", "FAIL": "FAIL", "SKIP": "skip", "UNKNOWN": " ?  "}


class Context:
    def __init__(self, system: System, args: argparse.Namespace):
        self.system = system
        self.args = args
        self.inspection = Inspection(system, cwd=os.getcwd())
        self.redactor = Redactor.for_env(system.env)


def doctor_lines(results: list[Any]) -> list[str]:
    lines = []
    for r in results:
        lines.append(f"[{SYMBOL[r.status.value]}] {r.check_id:28} {r.summary}")
        if r.status in (Status.FAIL, Status.WARN, Status.UNKNOWN) and r.suggested_fix:
            lines.append(f"       fix: {r.suggested_fix}")
    return lines


def doctor_result(ctx: Context, profile_name: str, categories: set[str] | None = None) -> Result:
    profile = resolve(profile_name)
    results = doctor.run(ctx.inspection, profile)
    if categories:
        results = [r for r in results if r.category in categories]
    counts = doctor.summary(results)
    code = ExitCode.VERIFICATION_FAILED if counts["FAIL"] else ExitCode.OK
    payload = {"profile": profile.name, "environment": ctx.inspection.kind, "summary": counts, "checks": [r.to_dict() for r in results]}
    head = [f"jadis doctor: profile {profile.name} on {ctx.inspection.kind}"]
    tail = ["", "  ".join(f"{k} {v}" for k, v in counts.items()), *([f"note: {n}" for n in profile.notes])]
    return code, payload, head + doctor_lines(results) + tail


# commands ----------------------------------------------------------------------------------------------------


def cmd_env(ctx: Context) -> Result:
    if ctx.args.env_cmd == "diff":
        try:
            old, new = (json.loads(open(p).read()) for p in (ctx.args.old, ctx.args.new))
        except (OSError, ValueError) as exc:
            return ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
        old = old.get("environment", old)
        new = new.get("environment", new)
        changes = report.diff(old, new, include_volatile=ctx.args.all)
        return ExitCode.OK, {"changes": changes}, [f"{c['key']}: {c['old']} -> {c['new']}" for c in changes] or ["no differences"]
    fp = ctx.inspection.fingerprint(include_tools=not ctx.args.no_tools)
    c = fp["classification"]
    lines = [
        f"environment   {c['kind']} ({c['confidence']} confidence)",
        f"distribution  {fp['distribution']} {fp['distribution_version']} ({fp['distribution_codename']})",
        f"architecture  {fp['architecture']}   kernel {fp['kernel']}   libc {fp['libc']}",
        f"identity      uid {fp['identity']['uid']}  root {fp['identity']['root']}  sudo {fp['identity']['sudo']}",
        f"shell         {fp['shell']['login_shell']}   package manager {fp['package_manager']['native']}",
        f"memory        {fp['memory']['total_mib']} MiB total, {fp['memory']['available_mib']} MiB available",
        f"disk (~)      {fp['disk']['free_mib']} MiB free of {fp['disk']['total_mib']} MiB",
        f"storage       {fp['storage']}",
    ]
    lines += [f"ambiguity     {a}" for a in c["ambiguities"]]
    lines += [f"leak          {leak['note']}: {leak['path']}" for leak in fp["package_manager"]["leaked"]]
    if "tools" in fp:
        lines.append("tools")
        for name, t in fp["tools"].items():
            if t.get("present") is True:
                extra = f" [{t.get('origin')}]" + (f" shadowed by {t['shadowed_by']}" if t.get("shadowed_by") else "")
                lines.append(f"  {name:13} {str(t.get('version')):14} {t['path']}{extra}")
        missing = [n for n, t in fp["tools"].items() if t.get("present") is False]
        lines.append(f"  not installed: {', '.join(missing) or 'none'}")
    return ExitCode.OK, fp, lines


def cmd_info(ctx: Context) -> Result:
    fp = ctx.inspection.fingerprint(include_tools=False)
    c = fp["classification"]
    line = f"{c['kind']} · {fp['distribution']} {fp['distribution_version']} · {fp['architecture']} · uid {fp['identity']['uid']}"
    return (
        ExitCode.OK,
        {
            "kind": c["kind"],
            "confidence": c["confidence"],
            "distribution": fp["distribution"],
            "version": fp["distribution_version"],
            "architecture": fp["architecture"],
            "jadis": __version__,
        },
        [line],
    )


def cmd_doctor(ctx: Context) -> Result:
    return doctor_result(ctx, ctx.args.profile)


def scoped_doctor(profile: str, categories: set[str] | None = None) -> Callable[[Context], Result]:
    return lambda ctx: doctor_result(ctx, profile, categories)


def run_plans(ctx: Context, plan_list: list[Plan], dry_run: bool) -> Result:
    plan_list = [p for p in plan_list if not p.empty or p.notes]
    payload: dict[str, Any] = {"plans": [p.to_dict() for p in plan_list], "dry_run": dry_run}
    lines = []
    for p in plan_list:
        lines.append(f"{p.title}:")
        lines += [f"  - {m.description}{'' if m.reversible else '  (not automatically reversible)'}" for m in p.mutations]
        lines += [f"  note: {n}" for n in p.notes]
    if not any(not p.empty for p in plan_list):
        return ExitCode.OK, {**payload, "status": "nothing-to-do"}, lines + ["nothing to change"]
    if dry_run:
        return ExitCode.OK, {**payload, "status": "planned"}, lines + ["dry run: nothing was changed"]
    executor = Executor(ctx.system.env, RealSystem().run)
    auth = Authorization(yes=ctx.args.yes)
    outcomes, code = [], ExitCode.OK
    for p in plan_list:
        if p.empty:
            continue
        outcome = executor.apply(p, auth)
        outcomes.append({"plan": p.plan_id, "status": outcome.status, "run_id": outcome.run_id, "applied": outcome.applied, "error": outcome.error})
        lines.append(f"{p.title}: {outcome.status}" + (f" (run {outcome.run_id})" if outcome.run_id else "") + (f": {outcome.error}" if outcome.error else ""))
        if outcome.status in ("declined", "failed"):
            code = ExitCode.INCOMPLETE
    if code is ExitCode.INCOMPLETE and any(o["status"] == "declined" for o in outcomes):
        lines.append("not authorized: pass --yes, or answer y at an interactive terminal")
    return code, {**payload, "outcomes": outcomes}, lines


def cmd_repair(ctx: Context) -> Result:
    a = ctx.args
    if a.list:
        items = [{"id": k, "summary": v[0]} for k, v in repairs.REPAIRS.items()]
        return ExitCode.OK, {"repairs": items}, [f"{i['id']:22} {i['summary']}" for i in items]
    if a.rollback:
        executor = Executor(ctx.system.env, RealSystem().run)
        try:
            plan = executor.rollback_plan(a.rollback)
        except LookupError as exc:
            return ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
        lines = [f"{plan.title}:"] + [f"  - {m.description}" for m in plan.mutations] + [f"  note: {n}" for n in plan.notes]
        if a.dry_run or a.check:
            return ExitCode.OK, {"plan": plan.to_dict(), "dry_run": True}, lines + ["dry run: nothing was changed"]
        outcome = executor.apply_rollback(plan, Authorization(yes=a.yes))
        code = ExitCode.OK if outcome.status in ("applied", "nothing-to-do") else ExitCode.INCOMPLETE
        return code, {"plan": plan.to_dict(), "status": outcome.status, "applied": outcome.applied}, lines + [f"rollback: {outcome.status}"]
    try:
        plan_list = repairs.plans(ctx.inspection, a.ids or None)
    except KeyError as exc:
        return ExitCode.USAGE, {"error": f"unknown repair: {exc}"}, [f"jadis: unknown repair {exc}; see `jadis repair --list`"]
    return run_plans(ctx, plan_list, dry_run=a.dry_run or a.check)


def cmd_bootstrap(ctx: Context) -> Result:
    a = ctx.args
    try:
        profile = resolve(a.profile)
        result = bootstrap.build(ctx.inspection, profile, include_optional=a.optional)
    except ProfileError as exc:
        return ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
    except bootstrap.Unsupported as exc:
        return ExitCode.UNSUPPORTED, {"error": str(exc)}, [f"jadis: {exc}"]
    code, payload, lines = run_plans(ctx, [result.plan], dry_run=a.dry_run or a.plan)
    payload.update(present=result.present, unavailable=result.unavailable)
    return code, payload, [f"already present: {', '.join(result.present) or 'none'}", *lines]


def cmd_python(ctx: Context) -> Result:
    a = ctx.args
    if a.python_cmd == "status":
        tools = ctx.inspection.tools({"python3", "pip"})
        venv = os.path.join(os.getcwd(), ".venv")
        data = {"python3": tools.get("python3"), "pip": tools.get("pip"), "project_venv": os.path.isdir(venv), "active_venv": ctx.system.env.get("VIRTUAL_ENV")}
        return (
            ExitCode.OK,
            data,
            [
                f"python3 {tools['python3'].get('version')}  pip {tools['pip'].get('version')}",
                f"project .venv: {'yes' if data['project_venv'] else 'no'}   active venv: {data['active_venv'] or 'none'}",
                "activate: source .venv/bin/activate",
            ],
        )
    if a.python_cmd in ("doctor", "verify"):
        return doctor_result(ctx, "python", {"python", "tools"})
    target = os.path.abspath(a.dir)
    venv = os.path.join(target, ".venv")
    plan = Plan("python-venv", f"Project venv in {target}")
    if os.path.isdir(venv) and not a.recreate:
        plan.notes.append(f"{venv} already exists (use --recreate to rebuild it)")
    else:
        python = ctx.system.which("python3")
        if not python:
            return ExitCode.UNSUPPORTED, {"error": "python3 not found"}, ["jadis: python3 not found"]
        argv = [python, "-m", "venv", *(["--clear"] if a.recreate else []), venv]
        plan.mutations.append(Mutation("run", venv, {"argv": argv}, False, " ".join(argv)))
        plan.notes.append("global Python packages are never modified; install project dependencies inside the venv")
    return run_plans(ctx, [plan], dry_run=a.dry_run)


def cmd_backup(ctx: Context) -> Result:
    env = ctx.system.env
    if ctx.args.set == "list":
        items = backup.list_backups(env)
        return ExitCode.OK, {"backups": items}, [f"{b['id']}  {b['files']} file(s)" for b in items] or ["no backups"]
    manifest = backup.create(env, ctx.args.set)
    lines = [f"backup {manifest['id']}: {len(manifest['files'])} file(s)"] + [f"  skipped {s['path']}: {s['reason']}" for s in manifest["skipped"]]
    return ExitCode.OK, manifest, lines


def cmd_restore(ctx: Context) -> Result:
    env = ctx.system.env
    try:
        preview = backup.restore_preview(env, ctx.args.backup_id)
    except LookupError as exc:
        return ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
    lines = [f"  {p['action']:9} ~/{p['path']}" for p in preview]
    changes = [p for p in preview if p["action"] in ("create", "overwrite")]
    if ctx.args.dry_run or not changes:
        return ExitCode.OK, {"preview": preview, "dry_run": True}, lines + (["dry run: nothing was changed"] if changes else ["nothing to restore"])
    plan = Plan("restore", f"Restore {ctx.args.backup_id}", [Mutation("restore", p["path"], {}, True, f"{p['action']} ~/{p['path']}") for p in changes])
    if not Authorization(yes=ctx.args.yes).granted(plan):
        return ExitCode.INCOMPLETE, {"preview": preview, "status": "declined"}, lines + ["not authorized: pass --yes"]
    result = backup.restore(env, ctx.args.backup_id)
    return (
        ExitCode.OK,
        {"preview": preview, **result},
        lines + [f"restored {len(result['restored'])} file(s); previous state saved as {result['pre_restore_backup']}"],
    )


def cmd_report(ctx: Context) -> Result:
    try:
        snap = report.snapshot(ctx.inspection, resolve(ctx.args.profile))
    except ProfileError as exc:
        return ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
    snap = ctx.redactor.value(snap)
    lines = [f"snapshot of {snap['environment']['classification']['kind']} for profile {snap['profile']}: {snap['doctor']['summary']}"]
    if ctx.args.out:
        os.makedirs(os.path.dirname(os.path.abspath(ctx.args.out)), exist_ok=True)
        with open(ctx.args.out, "w") as handle:
            handle.write(json.dumps(snap, indent=1, sort_keys=True) + "\n")
        lines.append(f"written to {ctx.args.out}")
    return ExitCode.OK, snap, lines


def cmd_profiles(ctx: Context) -> Result:
    raw = raw_profiles()
    if ctx.args.profiles_cmd == "validate":
        problems = validate(raw, {t.name for t in probes.TOOLS}, set(doctor.REGISTRY))
        return (
            (ExitCode.VERIFICATION_FAILED if problems else ExitCode.OK),
            {"problems": problems, "profiles": sorted(raw)},
            problems or [f"{len(raw)} profiles valid"],
        )
    if ctx.args.profiles_cmd == "show":
        try:
            p = resolve(ctx.args.name, raw)
        except ProfileError as exc:
            return ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
        data = {
            "name": p.name,
            "summary": p.summary,
            "chain": p.chain,
            "environments": p.environments,
            "requirements": [vars(r) for r in p.requirements],
            "checks": [c[0] for c in p.checks],
            "packages": p.packages,
            "notes": p.notes,
        }
        lines = [f"{p.name}: {p.summary}", f"extends: {' -> '.join(p.chain)}"]
        lines += [f"  {'required' if r.required else 'optional'} {r.tool}" + (f" >= {r.minimum}" if r.minimum else "") for r in p.requirements]
        return ExitCode.OK, data, lines
    items = [{"name": n, "summary": d.get("summary", "")} for n, d in sorted(raw.items())]
    return ExitCode.OK, {"profiles": items}, [f"{i['name']:11} {i['summary']}" for i in items]


def cmd_termux(ctx: Context) -> Result:
    sub = ctx.args.termux_cmd
    if sub == "doctor":
        return doctor_result(ctx, "termux")
    fp = ctx.inspection.fingerprint(include_tools=False)
    if sub == "storage":
        return ExitCode.OK, fp["storage"], [f"{k}: {v}" for k, v in fp["storage"].items()]
    if sub == "proot":
        root = "/data/data/com.termux/files/usr/var/lib/proot-distro/installed-rootfs"
        distros = ctx.system.listdir(root) or []
        data = {"inside_proot_guest": fp["proot"], "installed_distributions": distros, "guest": fp["distribution"] if fp["proot"] else None}
        return (
            ExitCode.OK,
            data,
            [
                f"inside a PRoot guest: {fp['proot']}" + (f" ({fp['distribution']} {fp['distribution_version']})" if fp["proot"] else ""),
                f"proot-distro installed: {', '.join(distros) or 'none visible'}",
            ],
        )
    # packages
    if ctx.inspection.kind != "termux":
        return ExitCode.UNSUPPORTED, {"error": "not native Termux"}, ["jadis: `termux packages` lists Termux packages from inside native Termux only"]
    result = ctx.system.run(["dpkg-query", "-W", "-f", "${Package} ${Version}\\n"], timeout=20)
    if not result.ok:
        return ExitCode.INCOMPLETE, {"error": result.error or result.stderr.strip()}, ["jadis: could not list packages"]
    pkgs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, _, version = line.strip().partition(" ")
        if name:
            pkgs[name] = version
    return ExitCode.OK, {"count": len(pkgs), "packages": pkgs}, [f"{len(pkgs)} packages installed"]


def cmd_vulkan(ctx: Context) -> Result:
    if ctx.args.vulkan_cmd == "doctor":
        return doctor_result(ctx, "llm", {"gpu"})
    v = ctx.inspection.vulkan
    lines = [f"state: {v.get('state')}", f"loaders: {', '.join(v['loaders']) or 'none'}"] + [
        f"device: {d['name']} ({d['type']}, API {d['api']})" for d in v["devices"]
    ]
    return ExitCode.OK, v, lines


def cmd_completion(ctx: Context) -> Result:
    parser = build_parser()
    tree: dict[str, list[str]] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                subs = [n for a in sub._actions if isinstance(a, argparse._SubParsersAction) for n in a.choices]
                opts = [o for a in sub._actions for o in a.option_strings if o.startswith("--")]
                tree[name] = sorted(set(subs + opts))
    if ctx.args.shell == "bash":
        cases = "\n".join(f'    {k}) opts="{" ".join(v)}" ;;' for k, v in sorted(tree.items()))
        script = f"""# bash completion for jadis (generated by `jadis completion bash`)
_jadis() {{
  local cur=${{COMP_WORDS[COMP_CWORD]}} opts
  if [ "$COMP_CWORD" -eq 1 ]; then opts="{" ".join(sorted(tree))} --help --version"; else
  case "${{COMP_WORDS[1]}}" in
{cases}
    *) opts="" ;;
  esac; fi
  COMPREPLY=($(compgen -W "$opts" -- "$cur"))
}}
complete -F _jadis jadis
"""
    else:
        cases = "\n".join(f"    {k}) _values 'option' {' '.join(repr(x) for x in v)} ;;" for k, v in sorted(tree.items()) if v)
        script = f"""#compdef jadis
# zsh completion for jadis (generated by `jadis completion zsh`)
_jadis() {{
  if (( CURRENT == 2 )); then _values 'command' {" ".join(sorted(tree))}; return; fi
  case $words[2] in
{cases}
  esac
}}
compdef _jadis jadis
"""
    return ExitCode.OK, {"shell": ctx.args.shell, "script": script}, [script.rstrip("\n")]


def cmd_capabilities(ctx: Context) -> Result:
    items: list[dict[str, Any]] = [
        {"command": "info/env/doctor/report/profiles/*-doctor/vulkan status/termux storage|proot|packages", "mutates": False},
        {
            "command": "repair, bootstrap, python venv, restore, repair --rollback",
            "mutates": True,
            "requires": "--yes or interactive y; --dry-run never mutates",
        },
        {"command": "backup", "mutates": "jadis data directory only"},
        {
            "command": "blux-capability environment.inspect|environment.doctor|environment.snapshot|toolchain.inspect",
            "mutates": False,
            "note": "BLUX subprocess provider; read-only",
        },
    ]
    return (
        ExitCode.OK,
        {"capabilities": items},
        [f"{'mutates' if i['mutates'] is True else ('read-only' if i['mutates'] is False else 'own-data'):9} {i['command']}" for i in items],
    )


def cmd_version(ctx: Context) -> Result:
    return ExitCode.OK, {"jadis": __version__, "python": sys.version.split()[0]}, [f"jadis {__version__}"]


def cmd_blux(ctx: Context) -> Result:
    from jadis import blux_capability

    return blux_capability.handle(ctx, ctx.args.capability_id)


# parser ------------------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    p = argparse.ArgumentParser(
        prog="jadis", description="JADIS Toolbox: where am I, what do I have, what's broken, what can safely be fixed.", parents=[common]
    )
    p.add_argument("--version", action="version", version=f"jadis {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn: Callable[[Context], Result], help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text, parents=[common])
        sp.set_defaults(func=fn)
        return sp

    add("info", cmd_info, "one-line summary of this environment")
    e = add("env", cmd_env, "environment fingerprint (read-only)")
    e.add_argument("--no-tools", action="store_true", help="skip toolchain probes")
    es = e.add_subparsers(dest="env_cmd")
    d = es.add_parser("diff", help="compare two `jadis env --json` or `jadis report --json` files", parents=[common])
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--all", action="store_true", help="include volatile fields (memory, disk, time)")
    doc = add("doctor", cmd_doctor, "evaluate this environment against a profile (never mutates)")
    doc.add_argument("--profile", default="minimal")
    for name, profile, cats, help_text in (
        ("shell", "minimal", {"shell", "proot"}, "PATH, startup files, shadowed commands"),
        ("git", "git", {"git", "tools"}, "git identity and defaults"),
        ("ssh", "git", {"ssh"}, "~/.ssh permissions and agent"),
        ("java", "java", {"java", "tools"}, "JDK, JAVA_HOME, Gradle wrapper"),
        ("android", "android", {"android", "java", "tools"}, "Android SDK, build-tools, adb/fastboot"),
        ("debian", "debian", {"debian", "proot", "environment"}, "apt, locale, PRoot specifics"),
        ("llm", "llm", {"llm", "gpu", "tools"}, "llama.cpp build prerequisites and Vulkan"),
    ):
        sp = add(name, scoped_doctor(profile, cats), help_text + " (doctor view)")
        sp.add_subparsers(dest=f"{name}_cmd").add_parser("doctor", parents=[common])
    r = add("repair", cmd_repair, "plan and apply safe repairs (inspect -> plan -> authorize -> apply -> verify -> journal)")
    r.add_argument("ids", nargs="*", help="repair ids (default: all); see `jadis repair --list`")
    for flag in ("--dry-run", "--check"):
        r.add_argument(flag, action="store_true", help="show the plan; change nothing")
    r.add_argument("--yes", action="store_true", help="authorize the plan without a prompt")
    r.add_argument("--list", action="store_true", help="list available repairs")
    r.add_argument("--rollback", metavar="RUN_ID", help="reverse an applied run from the journal")
    b = add("bootstrap", cmd_bootstrap, "install a profile's missing tools with this environment's package manager")
    b.add_argument("profile", nargs="?", default="minimal")
    for flag in ("--dry-run", "--plan"):
        b.add_argument(flag, action="store_true", help="show the plan; change nothing")
    b.add_argument("--optional", action="store_true", help="include optional tools")
    b.add_argument("--yes", action="store_true")
    py = add("python", cmd_python, "Python interpreter, pip and project venv")
    pys = py.add_subparsers(dest="python_cmd", required=True)
    for n in ("status", "doctor", "verify"):
        pys.add_parser(n, parents=[common])
    pv = pys.add_parser("venv", help="create a project-local .venv", parents=[common])
    pv.add_argument("dir", nargs="?", default=".")
    pv.add_argument("--recreate", action="store_true")
    pv.add_argument("--dry-run", action="store_true")
    pv.add_argument("--yes", action="store_true")
    t = add("termux", cmd_termux, "native Termux specifics and the Termux/PRoot bridge")
    t.add_argument("termux_cmd", choices=["doctor", "storage", "packages", "proot"])
    v = add("vulkan", cmd_vulkan, "Vulkan loader and devices")
    v.add_argument("vulkan_cmd", choices=["status", "doctor"], nargs="?", default="status")
    bk = add("backup", cmd_backup, "snapshot shell or git configuration (no credentials)")
    bk.add_argument("set", choices=["shell", "git", "list"])
    rt = add("restore", cmd_restore, "restore a backup (shows the changes first)")
    rt.add_argument("backup_id")
    rt.add_argument("--dry-run", action="store_true")
    rt.add_argument("--yes", action="store_true")
    rp = add("report", cmd_report, "reproducibility snapshot (environment + doctor), secrets redacted")
    rp.add_argument("--profile", default="outer-void")
    rp.add_argument("--out", help="write the snapshot JSON here (for example .jadis/environment.json)")
    pr = add("profiles", cmd_profiles, "list, show or validate toolchain profiles")
    prs = pr.add_subparsers(dest="profiles_cmd")
    prs.add_parser("list", parents=[common])
    sh = prs.add_parser("show", parents=[common])
    sh.add_argument("name")
    prs.add_parser("validate", parents=[common])
    add("capabilities", cmd_capabilities, "what jadis can do, and which commands mutate")
    c = add("completion", cmd_completion, "print a bash or zsh completion script")
    c.add_argument("shell", choices=["bash", "zsh"])
    add("version", cmd_version, "print the version")
    bc = sub.add_parser("blux-capability", help="BLUX subprocess provider (read-only; request JSON on stdin)")
    bc.add_argument("capability_id")
    bc.set_defaults(func=cmd_blux, json=True)
    return p


def main(argv: list[str] | None = None, system: System | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0) if exc.code in (0, None) else int(ExitCode.USAGE)
    ctx = Context(system or RealSystem(), args)
    try:
        code, payload, lines = args.func(ctx)
    except ProfileError as exc:
        code, payload, lines = ExitCode.USAGE, {"error": str(exc)}, [f"jadis: {exc}"]
    except KeyboardInterrupt:
        code, payload, lines = ExitCode.INCOMPLETE, {"error": "interrupted"}, ["jadis: interrupted"]
    except Exception as exc:  # pragma: no cover - reported, never a traceback with secrets
        code, payload, lines = (
            ExitCode.INTERNAL,
            {"error": f"internal error: {type(exc).__name__}: {exc}"},
            [f"jadis: internal error: {type(exc).__name__}: {exc}"],
        )
    if args.command == "blux-capability":  # BLUX protocol: exactly one JSON object, nothing else
        sys.stdout.write(json.dumps(ctx.redactor.value(payload), sort_keys=True) + "\n")
    elif args.json:
        sys.stdout.write(json.dumps({"exit_code": int(code), **ctx.redactor.value(payload)}, indent=1, sort_keys=True) + "\n")
    else:
        sys.stdout.write("\n".join(ctx.redactor.text(line) for line in lines) + "\n")
    return int(code)
