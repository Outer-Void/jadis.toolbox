"""Doctor: healthy fixtures pass with evidence, broken ones fail correctly, offline is not broken."""

import pytest

from conftest import fixture_system
from jadis import doctor
from jadis.inspect import Inspection
from jadis.model import Check, Severity, Status
from jadis.profiles import resolve


def results(sysm, profile="minimal"):
    return {r.check_id: r for r in doctor.run(Inspection(sysm), resolve(profile))}


def test_healthy_debian_passes_with_evidence():
    r = results(fixture_system("debian13"), "python")
    for cid in ("env.classified", "path.duplicates", "tool.git", "tool.python3", "tool.pip", "python.venv-module"):
        assert r[cid].status is Status.PASS and r[cid].evidence, cid
    assert not [c for c in r.values() if c.status is Status.FAIL]


def test_pass_without_evidence_is_impossible():
    with pytest.raises(ValueError):
        Check("x", "y", Status.PASS, Severity.INFO, "claimed")


def test_broken_fixture_fails_correctly():
    s = fixture_system("debian13")
    del s.executables["git"]
    s.commands["/usr/bin/python3 --version"] = {"rc": 0, "stdout": "Python 3.8.10\n"}
    s.commands["python3 -c import venv, ensurepip"] = {"rc": 1, "stderr": "ModuleNotFoundError: No module named 'ensurepip'"}
    s.environ["PATH"] = "/usr/bin:/usr/bin:/nonexistent"
    r = results(s, "python")
    assert r["tool.git"].status is Status.FAIL
    assert r["tool.python3"].status is Status.FAIL and r["tool.python3"].expected == ">= 3.10"
    assert r["python.venv-module"].status is Status.FAIL
    assert r["path.duplicates"].status is Status.WARN and r["path.dead"].detected == ["/nonexistent"]


def test_proot_guest_flags_termux_leak():
    r = results(fixture_system("proot-debian13"))
    assert r["path.termux-leak"].status is Status.WARN
    assert r["path.termux-pkg"].severity is Severity.HIGH


def test_termux_storage_and_profile_scoping():
    r = results(fixture_system("termux-no-storage"), "termux")
    assert r["termux.storage"].status is Status.WARN
    r = results(fixture_system("debian13"), "full")
    assert r["termux.storage"].status is Status.SKIP and "does not apply" in r["termux.storage"].summary


def test_offline_never_fails_local_health():
    s = fixture_system("debian13")
    s.files["/proc/net/route"] = "Iface\tDestination\n"
    r = results(s)
    assert r["network.local"].status is Status.WARN and r["network.local"].network
    assert not [c for c in r.values() if c.status is Status.FAIL]
    s.unreadable.add("/proc/net/route")
    assert results(s)["network.local"].status is Status.UNKNOWN


def test_ssh_permissions_read_modes_never_contents():
    s = fixture_system("debian13")
    s.files.update({"/home/dev/.ssh/id_ed25519": "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nSECRET\n", "/home/dev/.ssh/id_ed25519.pub": "ssh-ed25519 AAA"})
    s.modes.update({"/home/dev/.ssh": 0o755, "/home/dev/.ssh/id_ed25519": 0o644})
    reads = []
    original = s.read_text
    s.read_text = lambda p, limit=0: (reads.append(p), original(p))[1]
    r = doctor.run(Inspection(s), resolve("git"))
    fails = [c for c in r if c.status is Status.FAIL and c.category == "ssh"]
    assert len(fails) == 2 and all(c.auto_fixable for c in fails)
    assert "/home/dev/.ssh/id_ed25519" not in reads


def test_dangling_android_sdk_points_at_its_definition():
    s = fixture_system("proot-debian13")
    s.environ.update(ANDROID_HOME="/opt/android-sdk", ANDROID_SDK_ROOT="/opt/android-sdk")
    s.files["/home/dev/.zshrc"] = "x=1\nexport ANDROID_HOME=/opt/android-sdk\n"
    s.files["/home/dev/android-sdk/platforms/android-36/android.jar"] = "x"
    r = results(s, "android")["android.sdk"]
    assert r.status is Status.FAIL and r.auto_fixable
    assert r.detected["defined_in"] == ["~/.zshrc:2 (ANDROID_HOME)"]


def test_jdk_mismatch_is_reported():
    s = fixture_system("debian13")
    s.environ["JAVA_HOME"] = "/usr/lib/jvm/java-17"
    s.files["/usr/lib/jvm/java-17/bin/java"] = "x"
    s.executables["java"] = "/usr/bin/java"
    s.commands["/usr/bin/java -version"] = {"rc": 0, "stderr": 'openjdk version "21.0.4"\n'}
    s.commands["/usr/lib/jvm/java-17/bin/java -version"] = {"rc": 0, "stderr": 'openjdk version "17.0.12"\n'}
    assert results(s, "java")["java.java-home"].status is Status.WARN


def test_a_crashing_check_is_contained(monkeypatch):
    monkeypatch.setitem(doctor.REGISTRY, "disk.free", lambda i: 1 / 0)
    r = results(fixture_system("debian13"))
    assert r["disk.free"].status is Status.UNKNOWN and r["tool.git"].status is Status.PASS


def test_unknown_environment_is_reported_not_guessed():
    r = results(fixture_system("ambiguous-android-debian"))
    assert r["env.classified"].status is Status.UNKNOWN and r["env.classified"].severity is Severity.HIGH
