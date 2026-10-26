"""CLI contract, profiles, completions, and the optional BLUX boundary."""

import io
import json
import re
from pathlib import Path

from conftest import fixture_system, run_cli
from jadis import doctor, probes
from jadis.profiles import raw_profiles, resolve, validate

SRC = Path(__file__).resolve().parent.parent / "src" / "jadis"


def test_exit_codes():
    assert run_cli(["doctor"], fixture_system("debian13"))[0] == 0
    s = fixture_system("debian13")
    del s.executables["git"]
    assert run_cli(["doctor"], s)[0] == 1  # verification failed
    assert run_cli(["doctor", "--profile", "nope"], s)[0] == 2  # usage
    assert run_cli(["frobnicate"], s)[0] == 2
    assert run_cli(["bootstrap", "minimal", "--dry-run"], fixture_system("ambiguous-android-debian"))[0] == 3  # unsupported
    assert run_cli(["repair", "ssh-permissions", "--yes", "--rollback", "no-such-run"], s)[0] == 2


def test_json_and_human_render_the_same_result():
    s = fixture_system("debian13")
    code, data = run_cli(["doctor", "--json"], s)
    _, text = run_cli(["doctor"], fixture_system("debian13"))
    assert data["exit_code"] == code == 0
    for c in data["checks"]:
        assert c["check_id"] in text


def test_profiles_are_valid_and_validator_rejects_bad_ones():
    raw = raw_profiles()
    assert validate(raw, {t.name for t in probes.TOOLS}, set(doctor.REGISTRY)) == []
    bad = json.loads(json.dumps(raw))
    bad["minimal"]["requires"].append({"tool": "nonexistent-tool"})
    bad["minimal"]["checks"].append("no.such.check")
    bad["python"]["packages"]["apt"]["python3"] = "BAD NAME"
    bad["git"]["extends"] = ["git"]
    problems = validate(bad, {t.name for t in probes.TOOLS}, set(doctor.REGISTRY))
    assert len(problems) >= 4 and any("cycle" in p for p in problems)
    full = resolve("full")
    assert {"outer-void", "android", "llm", "termux"} <= set(full.chain)
    assert next(r for r in resolve("outer-void").requirements if r.tool == "python3").minimum == "3.11"


def test_completions_are_generated_from_the_parser():
    _, bash = run_cli(["completion", "bash"], fixture_system("debian13"))
    _, zsh = run_cli(["completion", "zsh"], fixture_system("debian13"))
    for cmd in ("doctor", "env", "repair", "bootstrap", "python"):
        assert cmd in bash and cmd in zsh
    assert "complete -F _jadis jadis" in bash and "#compdef jadis" in zsh


def test_env_diff(tmp_path):
    a, b = fixture_system("debian13"), fixture_system("debian13")
    b.commands["/usr/bin/git --version"] = {"rc": 0, "stdout": "git version 2.51.0\n"}
    (tmp_path / "a.json").write_text(json.dumps(run_cli(["env", "--json"], a)[1]))
    (tmp_path / "b.json").write_text(json.dumps(run_cli(["env", "--json"], b)[1]))
    _, out = run_cli(["env", "diff", str(tmp_path / "a.json"), str(tmp_path / "b.json"), "--json"], a)
    assert [c["key"] for c in out["changes"]] == ["tools.git.version"]


def test_blux_capabilities_are_read_only_and_follow_the_protocol(monkeypatch):
    s = fixture_system("debian13")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"capability_id": "environment.doctor", "input": {"profile": "git"}})))
    code, out = run_cli(["blux-capability", "environment.doctor"], s)
    assert code == 0 and out["profile"] == "git" and "exit_code" not in out
    for mutating in ("environment.repair", "environment.bootstrap", "toolchain.install"):
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        code, out = run_cli(["blux-capability", mutating], s)
        assert code == 1 and out["error"]["code"] == "UNSUPPORTED_CAPABILITY"


def test_blux_manifest_declares_only_read_only_capabilities():
    caps = (SRC.parent.parent / ".blux" / "capabilities.yaml").read_text()
    ids = re.findall(r"capability_id:\s*(\S+)", caps)
    assert sorted(ids) == ["environment.doctor", "environment.inspect", "environment.snapshot", "toolchain.inspect"]
    assert re.findall(r"side_effects:\s*(\S+)", caps) == ["read"] * 4


def test_standalone_without_blux():
    for f in SRC.rglob("*.py"):
        text = f.read_text()
        assert not re.search(r"^\s*(import|from)\s+blux", text, re.M), f
