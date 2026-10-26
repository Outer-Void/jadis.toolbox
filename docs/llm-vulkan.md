# Local LLMs (llama.cpp) and Vulkan

Replaces `termux-llm-vulcan.md`, which was removed on 2026-10-26 as incorrect (see [migration.md](migration.md)).

## 1. Check first

```sh
jadis llm            # cmake, compilers, git, llama.cpp binaries, Vulkan state
jadis vulkan status  # loaders, vulkaninfo, devices (GPU vs software)
```

Vulkan states:

| State | Meaning |
|---|---|
| `no Vulkan loader` | No `libvulkan` found |
| `no vulkaninfo` | A loader exists, but the tools are not installed |
| `vulkaninfo failed` | The driver is unusable (the error is shown) |
| `software only` | A CPU implementation such as llvmpipe |
| `gpu` | At least one real GPU device |

Without a GPU, llama.cpp still runs on the CPU.

## 2. Tools

| Environment | Command |
|---|---|
| Termux | `jadis bootstrap llm --plan`, then `pkg install cmake clang make git vulkan-tools` |
| Debian / PRoot Debian | `jadis bootstrap llm --plan`, then `sudo apt-get install cmake gcc make git vulkan-tools` |

## 3. GPU drivers: hardware-specific, your decision

jadis never installs GPU drivers. Android GPU access from Termux depends on the device and its vendor
driver:
- Termux packages (for example from the `tur-repo` and `x11-repo` repositories) may provide working Vulkan
  ICDs for some devices.
- Third-party `.deb` drivers from tutorial repositories are **untrusted binaries**. Install one only if you
  trust its source, verify its checksum, and accept that it can break or be unsupported on your device.
  Record what you installed.
- Inside PRoot, the guest does not get the Android GPU driver automatically. Expect `software only` unless
  you know otherwise.

## 4. Build llama.cpp

```sh
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build                       # CPU build: always works
cmake -B build -DGGML_VULKAN=ON      # Vulkan build: only when `jadis vulkan status` says gpu
cmake --build build --config Release -j2
```

The Vulkan build also needs Vulkan headers and `glslc`/shaderc. See llama.cpp's own
[build documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md), which is
authoritative and changes often.

## 5. Run

```sh
./build/bin/llama-cli -m models/<model>.gguf
./build/bin/llama-server -m models/<model>.gguf --host 127.0.0.1 --port 8080
```

Serve on **127.0.0.1**. Do not use `--host 0.0.0.0` unless you deliberately want other devices on the
network to reach an unauthenticated model server. `-ngl N` offloads N layers to the GPU; start low on phones.

Models come from their publishers, for example GGUF repositories on Hugging Face. Check each model's licence.
