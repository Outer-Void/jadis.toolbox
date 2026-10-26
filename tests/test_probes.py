"""Probes fail independently, stay within two concurrent workers, and expose shadows and leaks."""

import threading
import time

from conftest import fixture_system
from jadis import probes
from jadis.inspect import Inspection
from jadis.system import FakeSystem, RunResult


def test_versions_parse_from_fixture():
    tools = Inspection(fixture_system("debian13")).tools({"git", "python3", "pip", "curl"})
    assert tools["git"]["version"] == "2.47.3" and tools["python3"]["version"] == "3.13.5" and tools["pip"]["version"] == "25.1.1"


def test_missing_crashing_timeout_and_malformed_tools_are_isolated():
    s = fixture_system("debian13")
    s.executables.update(node="/usr/bin/node", java="/usr/bin/java", cmake="/usr/bin/cmake")
    s.commands["/usr/bin/node --version"] = {"error": "timed out after 10s"}
    s.commands["/usr/bin/java -version"] = {"rc": 0, "stdout": "\x00\xff garbage", "stderr": ""}
    s.commands["/usr/bin/cmake --version"] = {"error": "permission denied"}
    tools = Inspection(s).tools({"node", "java", "cmake", "git", "gradle"})
    assert tools["node"]["error"].startswith("timed out") and tools["node"]["version"] == "unknown"
    assert tools["java"]["error"] == "unrecognized version output"
    assert tools["cmake"]["error"] == "permission denied"
    assert tools["gradle"]["present"] is False
    assert tools["git"]["version"] == "2.47.3"  # unaffected


def test_a_probe_that_raises_does_not_stop_the_others(monkeypatch):
    real = probes.probe_tool

    def explode(system, spec):
        if spec.name == "git":
            raise RuntimeError("boom")
        return real(system, spec)

    monkeypatch.setattr(probes, "probe_tool", explode)
    tools = probes.probe_tools(fixture_system("debian13"), {"git", "curl"})
    assert "probe crashed" in tools["git"]["error"] and tools["curl"]["version"] == "8.14.1"


def test_at_most_two_probes_run_at_once():
    class Slow(FakeSystem):
        active = 0
        peak = 0
        lock = threading.Lock()

        def run(self, argv, timeout=10.0):
            with self.lock:
                Slow.active += 1
                Slow.peak = max(Slow.peak, Slow.active)
            time.sleep(0.02)
            with self.lock:
                Slow.active -= 1
            return RunResult(0, "v 1.2.3")

    s = Slow(environ={}, executables={t.name: f"/usr/bin/{t.argv[0]}" for t in probes.TOOLS})
    probes.probe_tools(s)
    assert Slow.peak == 2


def test_shadowed_grep_and_termux_origin():
    s = fixture_system("proot-debian13")
    s.links["/usr/bin/grep"] = "/usr/bin/ugrep"
    s.executables["clang"] = "/data/data/com.termux/files/usr/bin/clang"
    s.commands["/data/data/com.termux/files/usr/bin/clang --version"] = {"rc": 0, "stdout": "clang version 21.1.0\n"}
    tools = Inspection(s).tools({"grep", "clang"})
    assert tools["grep"]["shadowed_by"] == "ugrep"
    assert tools["clang"]["origin"] == "termux"


def test_android_sdk_detail_and_arch_mismatch():
    s = fixture_system("proot-debian13")
    sdk = "/home/dev/android-sdk"
    s.environ["ANDROID_HOME"] = sdk
    s.files.update(
        {
            f"{sdk}/platforms/android-36/android.jar": "x",
            f"{sdk}/build-tools/36.0.0/aapt2": "@elf:x86_64",
            f"{sdk}/build-tools/36.0.0/apksigner": "x",
            f"{sdk}/platform-tools/adb": "x",
        }
    )
    data = Inspection(s).android_sdk
    assert data["platform_jars"] == ["android-36"]
    assert data["build_tools_detail"]["36.0.0"]["aapt2_arch"] == "x86_64" and data["build_tools_detail"]["36.0.0"]["aapt2_runs_here"] is False


def test_sdk_candidates_dedupe_bind_mounts():
    s = fixture_system("proot-debian13")
    a, b = "/home/dev/android-sdk", "/data/data/com.termux/files/home/android-sdk"
    s.files.update({f"{a}/build-tools/36.0.0/aapt2": "x", f"{b}/build-tools/36.0.0/aapt2": "x"})
    assert probes.sdk_candidates(s) == [a, b]
    s.same_as[b] = a
    assert probes.sdk_candidates(s) == [a]


def test_vulkan_states():
    s = fixture_system("debian13")
    assert probes.vulkan(s)["state"] == "no Vulkan loader"
    s.files["/usr/lib/x86_64-linux-gnu/libvulkan.so.1"] = "x"
    assert probes.vulkan(s)["state"] == "no vulkaninfo"
    s.executables["vulkaninfo"] = "/usr/bin/vulkaninfo"
    s.commands["vulkaninfo --summary"] = {"rc": 0, "stdout": "deviceName = llvmpipe (LLVM 19)\napiVersion = 1.4.305\ndeviceType = PHYSICAL_DEVICE_TYPE_CPU\n"}
    assert probes.vulkan(s)["state"] == "software only"
    s.commands["vulkaninfo --summary"] = {
        "rc": 0,
        "stdout": "deviceName = Adreno (TM) 740\napiVersion = 1.3.128\ndeviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU\n",
    }
    assert probes.vulkan(s)["state"] == "gpu"
    s.commands["vulkaninfo --summary"] = {"rc": 1, "stdout": "", "stderr": "ERROR_INCOMPATIBLE_DRIVER"}
    assert probes.vulkan(s)["state"] == "vulkaninfo failed"
