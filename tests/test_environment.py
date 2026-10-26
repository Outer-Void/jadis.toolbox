"""Hard gate: environment classification. Ambiguity gives UNKNOWN, never false certainty."""

import itertools

import pytest

from conftest import fixture_system
from jadis.environment import Signals, classify, detect_signals, parse_os_release
from jadis.inspect import Inspection
from jadis.system import FakeSystem


@pytest.mark.parametrize(
    "name,kind",
    [
        ("termux", "termux"),
        ("termux-no-storage", "termux"),
        ("proot-debian13", "proot-debian"),
        ("debian13", "debian"),
        ("ci-debian13", "debian"),
        ("ambiguous-android-debian", "unknown"),
        ("blank", "unknown"),
    ],
)
def test_fixtures_classify(name, kind):
    assert Inspection(fixture_system(name)).kind == kind


def test_proot_debian_facts_and_leak():
    fp = Inspection(fixture_system("proot-debian13")).fingerprint(include_tools=False)
    assert (fp["distribution"], fp["distribution_version"], fp["architecture"]) == ("debian", "13", "aarch64")
    assert fp["kernel"] == "6.17.0-PRoot-Distro" and fp["proot"] and fp["android"] and fp["libc"].startswith("glibc")
    assert fp["package_manager"]["native"] == "apt-get"
    assert fp["package_manager"]["leaked"][0]["name"] == "pkg"
    assert fp["classification"]["confidence"] == "high"


def test_termux_facts():
    fp = Inspection(fixture_system("termux")).fingerprint(include_tools=False)
    assert fp["termux"] and fp["libc"] == "bionic" and fp["package_manager"]["native"] == "pkg"
    assert fp["storage"]["android_shared_storage"] == "readable"
    no = Inspection(fixture_system("termux-no-storage")).fingerprint(include_tools=False)
    assert no["storage"]["android_shared_storage"] == "not readable" and "termux-setup-storage" in no["storage"]["setup_hint"]


def test_ci_is_a_flag_not_a_kind():
    i = Inspection(fixture_system("ci-debian13"))
    assert i.kind == "debian" and i.signals.ci


def test_unknown_values_are_unknown_not_invented():
    fp = Inspection(fixture_system("blank")).fingerprint(include_tools=False)
    assert fp["distribution"] == "unknown" and fp["architecture"] == "unknown" and fp["memory"]["total_mib"] == "unknown"
    assert fp["classification"]["ambiguities"]


def test_ptrace_by_something_else_is_not_proot():
    sysm = fixture_system("debian13")
    sysm.files["/proc/self/status"] = "TracerPid:\t77\n"
    sysm.files["/proc/77/comm"] = "gdb\n"
    assert Inspection(sysm).kind == "debian"


def test_os_release_parsing_is_tolerant():
    assert parse_os_release("ID=\"debian\"\n# c\nbad line\nVERSION_ID='13'\nlower=x\n") == {"ID": "debian", "VERSION_ID": "13"}
    assert parse_os_release(None) == {}


def test_classifier_invariants_over_every_signal_combination():
    for android, prefix, tracer, kernel, distro in itertools.product([0, 1], [0, 1], [0, 1], [0, 1], ["", "debian", "ubuntu", "fedora"]):
        s = Signals(
            android=bool(android),
            termux_prefix=bool(prefix),
            proot_tracer=bool(tracer),
            proot_kernel=bool(kernel),
            os_release={"ID": distro, "ID_LIKE": "debian" if distro == "ubuntu" else ""} if distro else {},
        )
        c = classify(s)
        if c.kind == "termux":
            assert prefix and android and not (tracer or kernel)
        if c.kind.startswith("proot"):
            assert (tracer or kernel) and distro
        if c.kind in ("debian", "debian-family", "linux-other"):
            assert not android and not prefix and not (tracer or kernel)
        if c.kind == "unknown":
            assert c.ambiguities, s


def test_one_broken_signal_source_does_not_stop_detection():
    sysm = fixture_system("debian13")
    sysm.commands["uname -m"] = {"error": "permission denied"}
    sysm.unreadable.add("/proc/self/status")
    s = detect_signals(sysm)
    assert s.architecture == "unknown" and s.os_release["ID"] == "debian"
    assert classify(s).kind == "debian"


def test_misclassification_guard_termux_prefix_without_android():
    sysm = FakeSystem(environ={"HOME": "/h", "PREFIX": "/data/data/com.termux/files/usr"}, files={"/etc/os-release": "ID=debian\n"})
    assert Inspection(sysm).kind == "unknown"
