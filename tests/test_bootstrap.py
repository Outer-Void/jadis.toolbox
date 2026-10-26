"""Bootstrap plans use only this environment's package manager and never reinstall working tools."""

import pytest

from conftest import fixture_system
from jadis import bootstrap
from jadis.inspect import Inspection
from jadis.profiles import resolve


def plan(sysm, profile="minimal", optional=False):
    return bootstrap.build(Inspection(sysm), resolve(profile), include_optional=optional)


def test_termux_uses_termux_pkg_only():
    s = fixture_system("termux")
    del s.executables["git"]
    argv = plan(s).plan.mutations[0].detail["argv"]
    assert argv[0] == "/data/data/com.termux/files/usr/bin/pkg" and argv[1:] == ["install", "-y", "git"]


def test_debian_uses_apt_with_sudo_and_skips_present_tools():
    s = fixture_system("debian13")
    del s.executables["curl"]
    r = plan(s)
    argv = r.plan.mutations[0].detail["argv"]
    assert argv == ["/usr/bin/sudo", "/usr/bin/apt-get", "install", "-y", "--no-install-recommends", "curl"]
    assert "git" in r.present and "tar" in r.present


def test_root_needs_no_sudo_and_no_root_no_sudo_is_refused():
    s = fixture_system("debian13")
    del s.executables["curl"]
    s.user_id = 0
    assert plan(s).plan.mutations[0].detail["argv"][0] == "/usr/bin/apt-get"
    s.user_id = 1000
    del s.executables["sudo"]
    with pytest.raises(bootstrap.Unsupported, match="root or sudo"):
        plan(s)


def test_proot_guest_never_uses_leaked_termux_pkg_or_binaries():
    s = fixture_system("proot-debian13")
    s.executables["git"] = "/data/data/com.termux/files/usr/bin/git"
    s.commands["/data/data/com.termux/files/usr/bin/git --version"] = {"rc": 0, "stdout": "git version 2.51.0\n"}
    r = plan(s)
    argv = r.plan.mutations[0].detail["argv"]
    assert argv[:2] == ["/usr/bin/sudo", "/usr/bin/apt-get"] and argv[-1] == "git"
    assert not any("com.termux" in a for a in argv)
    assert any("Termux's" in n for n in r.plan.notes) and any("PRoot" in n for n in r.plan.notes)


def test_everything_present_plans_nothing():
    assert plan(fixture_system("debian13")).plan.empty


def test_unsupported_environment_and_missing_mappings():
    with pytest.raises(bootstrap.Unsupported):
        plan(fixture_system("ambiguous-android-debian"))
    s = fixture_system("termux")
    r = plan(s, "llm", optional=True)
    assert "gcc" in r.unavailable  # Termux has no gcc package; nothing is guessed
