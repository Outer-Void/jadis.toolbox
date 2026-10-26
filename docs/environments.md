# Environments

## Detection

Each signal records its evidence (`jadis env --json` → `classification.reasons`).

| Signal | Source |
|---|---|
| Android | `$ANDROID_ROOT`, or `/system/build.prop` |
| Termux | `$PREFIX` ending in `com.termux/files/usr`, or `$TERMUX_VERSION`; `…/usr/bin/pkg` visible |
| PRoot | The tracer in `/proc/self/status` is a process named `proot` (strong), or the kernel release contains "PRoot" (`proot-distro` sets this through `uname`). `PROOT_*` variables are supporting evidence only |
| Distribution | `/etc/os-release` |
| CI | `$CI` / `$GITHUB_ACTIONS` (a flag, not a kind) |

## Classification

| Kind | Rule |
|---|---|
| `proot-debian` / `proot-other` | PRoot evidence plus an os-release |
| `termux` | Termux prefix plus Android, without PRoot |
| `debian` / `debian-family` / `linux-other` | No Android, no PRoot; classified by os-release `ID` / `ID_LIKE` |
| `unknown` | Anything else, with the reasons: Android signals without Termux or PRoot, PRoot without os-release, a Termux prefix without Android, no os-release |

An exhaustive test over every combination of signals checks these invariants. A process traced by something
other than proot (for example gdb) is not PRoot.

## Native Termux

- Package manager `pkg`, libc `bionic`, never root.
- Shared storage needs `termux-setup-storage`. jadis can only tell you to run it: the permission prompt needs
  you on the device.
- `jadis termux doctor|storage|packages|proot`. Bootstrap uses `$PREFIX/bin/pkg` only.
- Termux has no `gcc` package (use `clang`). Profiles say so instead of guessing.

## PRoot Debian (`proot-distro login debian`)

What to expect:
- **Fake root.** Root inside the guest has no real privilege, and files it creates are root-owned. jadis
  suggests `--user`.
- **No systemd** and no services. PRoot is not kernel isolation, and the Android kernel is shared.
- **Syscall translation** slows I/O-heavy builds.

What jadis reports:
- **Leaks across the boundary:** Termux's `PREFIX/bin` on the guest PATH, Termux's `pkg` callable from the
  guest, and host `ANDROID_*` variables. Bootstrap never uses leaked Termux binaries; it plans the guest's
  own Debian packages. Termux binaries run in the guest, but they are Bionic and bypass apt.
- **One SDK, two paths:** `~` inside the guest and Termux's home can be the same directory through a bind
  mount. jadis compares device and inode, so one SDK seen twice counts once.

## Native Debian 13

`apt-get` via root or sudo. Without either, bootstrap refuses rather than half-running. The locale is
checked, since non-UTF-8 locales mangle tool output.

## CI / non-interactive

Mutations need `--yes`. The CI workflow runs a real `debian:13` container job (root, no sudo) next to the
Ubuntu matrix. CI has no Termux or Android: those paths are fixture-tested.
