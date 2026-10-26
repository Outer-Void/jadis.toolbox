"""Regenerate tests/fixtures/*.json (synthetic machines). Run: python3 tests/make_fixtures.py"""

import json
from pathlib import Path

T = "/data/data/com.termux/files"
DEBIAN13 = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME="Debian GNU/Linux"\nVERSION_ID="13"\nVERSION_CODENAME=trixie\nID=debian\n'
MEMINFO = "MemTotal:        5582336 kB\nMemFree:          400000 kB\nMemAvailable:    1691648 kB\n"
ROUTE = "Iface\tDestination\tGateway\nwlan0\t00000000\t0101A8C0\n"


def tool(path, out, argv=None):
    return path, out, argv


def base(home):
    return {
        "env": {"HOME": home},
        "executables": {},
        "commands": {},
        "files": {},
        "modes": {},
        "links": {},
        "disk": {home: [30 * 2**30, 100 * 2**30]},
        "uid": 1000,
    }


def add(fx, name, path, argv_tail, out, rc=0, stderr=""):
    fx["executables"][name] = path
    fx["commands"][" ".join([path, *argv_tail])] = {"rc": rc, "stdout": out, "stderr": stderr}


def common_tools(fx, prefix):
    add(fx, "git", f"{prefix}/git", ["--version"], "git version 2.47.3\n")
    add(fx, "curl", f"{prefix}/curl", ["--version"], "curl 8.14.1 (aarch64-unknown-linux-gnu)\n")
    add(fx, "tar", f"{prefix}/tar", ["--version"], "tar (GNU tar) 1.35\n")
    add(fx, "python3", f"{prefix}/python3", ["--version"], "Python 3.13.5\n")
    fx["commands"][f"{prefix}/python3 -m pip --version"] = {"rc": 0, "stdout": "pip 25.1.1 from /x (python 3.13)\n"}
    add(fx, "grep", f"{prefix}/grep", ["--version"], "grep (GNU grep) 3.11\n")
    add(fx, "sed", f"{prefix}/sed", ["--version"], "sed (GNU sed) 4.9\n")
    add(fx, "find", f"{prefix}/find", ["--version"], "find (GNU findutils) 4.10.0\n")
    fx["commands"]["git config --global --get user.name"] = {"rc": 0, "stdout": "Test User\n"}
    fx["commands"]["git config --global --get user.email"] = {"rc": 0, "stdout": "test@example.invalid\n"}
    fx["commands"]["git config --global --get init.defaultBranch"] = {"rc": 0, "stdout": "main\n"}
    fx["commands"]["python3 -c import venv, ensurepip"] = {"rc": 0, "stdout": ""}
    for d in prefix, "/usr/bin":
        fx["files"].setdefault(d, None)
    fx["files"]["/proc/meminfo"] = MEMINFO
    fx["files"]["/proc/net/route"] = ROUTE


def termux(storage=True):
    home = f"{T}/home"
    fx = base(home)
    fx["env"].update(PREFIX=f"{T}/usr", TERMUX_VERSION="0.118.3", ANDROID_ROOT="/system", SHELL=f"{T}/usr/bin/bash", PATH=f"{T}/usr/bin", LANG="en_US.UTF-8")
    fx["files"].update(
        {
            "/system/build.prop": "ro.build.version.sdk=36\n",
            f"{T}/usr/bin/pkg": "#!/bin/sh\n",
            "/proc/self/status": "Name:\tpython3\nTracerPid:\t0\n",
            "/proc/sys/kernel/osrelease": "6.1.99-android14\n",
            f"{home}/.bashrc": "alias ll='ls -l'\n",
        }
    )
    if storage:
        fx["files"]["/storage/emulated/0/Download"] = None
        fx["files"][f"{home}/storage"] = None
    fx["executables"]["pkg"] = f"{T}/usr/bin/pkg"
    fx["commands"]["uname -m"] = {"rc": 0, "stdout": "aarch64\n"}
    common_tools(fx, f"{T}/usr/bin")
    fx["files"].pop("/proc/net/route")  # Android hides the route table
    return fx


def proot_debian():
    home = "/home/dev"
    fx = base(home)
    fx["env"].update(ANDROID_ROOT="/system", PROOT_L2S_DIR="/x/.l2s", SHELL="/usr/bin/zsh", PATH=f"/usr/local/bin:/usr/bin:{T}/usr/bin", LANG="C.UTF-8")
    fx["files"].update(
        {
            "/etc/os-release": DEBIAN13,
            "/system/build.prop": "x\n",
            f"{T}/usr/bin/pkg": "#!/bin/sh\n",
            "/usr/local/bin": None,
            "/proc/self/status": "Name:\tpython3\nTracerPid:\t4242\n",
            "/proc/4242/comm": "proot\n",
            f"{home}/.zshrc": "export PATH\n",
            "/storage/emulated/0/Download": None,
            f"{T}/usr/bin": None,
        }
    )
    fx["commands"]["uname -m"] = {"rc": 0, "stdout": "aarch64\n"}
    fx["commands"]["uname -r"] = {"rc": 0, "stdout": "6.17.0-PRoot-Distro\n"}
    fx["commands"]["ldd --version"] = {"rc": 0, "stdout": "ldd (Debian GLIBC 2.41-12) 2.41\n"}
    common_tools(fx, "/usr/bin")
    fx["executables"].update({"apt-get": "/usr/bin/apt-get", "sudo": "/usr/bin/sudo", "pkg": f"{T}/usr/bin/pkg"})
    return fx


def debian(ci=False):
    home = "/home/dev"
    fx = base(home)
    fx["env"].update(SHELL="/bin/bash", PATH="/usr/local/bin:/usr/bin:/bin", LANG="C.UTF-8")
    if ci:
        fx["env"].update(CI="true", GITHUB_ACTIONS="true")
    fx["files"].update(
        {
            "/etc/os-release": DEBIAN13,
            "/proc/self/status": "Name:\tpython3\nTracerPid:\t0\n",
            "/proc/sys/kernel/osrelease": "6.12.48-amd64\n",
            "/usr/local/bin": None,
            "/bin": None,
            f"{home}/.bashrc": "# user config\nexport EDITOR=vi\n",
        }
    )
    fx["commands"]["uname -m"] = {"rc": 0, "stdout": "x86_64\n"}
    fx["commands"]["ldd --version"] = {"rc": 0, "stdout": "ldd (Debian GLIBC 2.41-12) 2.41\n"}
    common_tools(fx, "/usr/bin")
    fx["executables"].update({"apt-get": "/usr/bin/apt-get", "sudo": "/usr/bin/sudo"})
    return fx


def ambiguous():
    fx = debian()
    fx["files"]["/system/build.prop"] = "x\n"  # Android host signal, Debian os-release, but no PRoot evidence
    return fx


def blank():
    return {"env": {"HOME": "/root"}, "executables": {}, "commands": {}, "files": {}, "uid": 0}


FIXTURES = {
    "termux": termux(),
    "termux-no-storage": termux(storage=False),
    "proot-debian13": proot_debian(),
    "debian13": debian(),
    "ci-debian13": debian(ci=True),
    "ambiguous-android-debian": ambiguous(),
    "blank": blank(),
}

if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures"
    for name, data in FIXTURES.items():
        (out / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print("wrote", ", ".join(FIXTURES))
