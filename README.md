# JADIS Toolbox

A portable workstation tool for the environments Outer Void is actually built in: **native Termux on
Android, Debian 13 under `proot-distro`, and native Debian 13**. `jadis` answers, from evidence:

> Where am I? What do I have? What's broken? What am I missing? What can safely be fixed? What exactly will
> change? Can this machine build what I need? Can I reproduce this environment later?

It is a standalone utility (Python 3.10+, standard library only). BLUX integration is optional and read-only.

**Maturity: `0.1.0`, early.** Evidence levels (details in [docs/testing.md](docs/testing.md)):

| Level | Status |
|---|---|
| Unit, fixture and integration tested | Yes |
| Build tested | Yes: a wheel installed into a clean virtualenv |
| PROOT_VALIDATED | Run for real on Debian 13 under PRoot |
| TERMUX_VALIDATED | **No** |
| DEBIAN_VALIDATED | **No** for native Debian 13, beyond the CI container job (pending its first run) |

## Install

```sh
git clone git@github.com:Outer-Void/jadis.toolbox.git && cd jadis.toolbox
python3 -m venv ~/.local/share/jadis/venv
~/.local/share/jadis/venv/bin/pip install .
ln -s ~/.local/share/jadis/venv/bin/jadis ~/.local/bin/jadis    # or: pipx install .
```

This never installs into the system Python. Debian 12+ marks it externally managed, and jadis respects
that. Works the same in Termux (`pkg install python git` first) and in PRoot Debian. There is no published
package or APT repository.

## Quick start

```sh
jadis info                          # one line: proot-debian · debian 13 · aarch64 · uid 1000
jadis env                           # full fingerprint (add --json for machines)
jadis doctor --profile outer-void   # what is broken or missing for Outer Void work
jadis repair --dry-run              # what could be fixed, exactly, without changing anything
jadis bootstrap python --plan       # what would be installed, with this environment's package manager
jadis report --out .jadis/environment.json   # reproducibility snapshot (secrets redacted)
jadis env diff old.json new.json    # "works in Termux but not in Debian": what differs
```

## Commands

| Command | Does | Mutates |
|---|---|---|
| `info`, `env [--no-tools]`, `env diff A B` | Classification, facts, toolchain versions and origins | no |
| `doctor --profile P` | Checks against a profile: PASS/WARN/FAIL/SKIP/UNKNOWN, each with evidence | no |
| `shell`, `git`, `ssh`, `java`, `android`, `debian`, `llm` | Focused doctor views (`jadis git doctor` works too) | no |
| `python status\|doctor\|verify`, `vulkan status\|doctor`, `termux doctor\|storage\|packages\|proot` | Toolchain-specific views | no |
| `profiles list\|show\|validate` | The declarative toolchain profiles | no |
| `report [--out FILE]` | Fingerprint plus doctor results, redacted | only `--out` |
| `repair [IDS] [--dry-run] [--yes]`, `repair --list`, `repair --rollback RUN` | Safe, journaled repairs | yes, authorized |
| `bootstrap P [--plan] [--optional] [--yes]` | Installs a profile's missing tools | yes, authorized |
| `python venv [DIR]` | Creates a project-local `.venv` | yes, authorized |
| `backup shell\|git\|list`, `restore ID [--dry-run] [--yes]` | Config snapshots without credentials | restore: authorized |
| `capabilities`, `completion bash\|zsh`, `version` | | no |

Profiles:

| Profile | Covers |
|---|---|
| `minimal` | Shell, PATH and core utilities |
| `git` | Git and SSH readiness |
| `python` | Interpreter, pip, venv |
| `node` | Node.js and npm |
| `java` | JDK for Gradle and Android builds |
| `android` | Command-line Android development (no Android Studio) |
| `llm` | llama.cpp prerequisites and optional Vulkan |
| `termux` | Native Termux specifics |
| `debian` | Debian and PRoot Debian specifics |
| `outer-void` | What the organization's project classes need |
| `full` | Everything above |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | a required check failed |
| 2 | usage error |
| 3 | unsupported environment |
| 4 | declined, partial or interrupted |
| 70 | internal error |

Details: [docs/cli.md](docs/cli.md).

## Safety model

- **Inspection never writes.** `env`, `doctor`, `report`, `repair --check/--dry-run` and
  `bootstrap --plan` perform zero filesystem or package changes; tests prove this on a real temporary
  home.
- **Mutation is plan → show → authorize → apply → verify → journal.** Without `--yes`, or a `y` typed at an
  interactive terminal, nothing changes (exit 4).
  - Shell files are only edited inside marked `# >>> jadis managed: … >>>` blocks, after a backup.
  - Every applied change is journaled, and `jadis repair --rollback RUN` reverses it.
- **Never touched:** identity (`user.name`/`user.email`), key contents, package sources, Android SDK layout,
  GPU drivers.
- **Secrets are redacted everywhere.** That covers token- and key-shaped strings, the values of
  secret-named variables wherever they appear, URL credentials and private-key blocks; `$HOME` is shown as
  `~`. The environment is never dumped. Diagnostics are never uploaded.
- **Offline first.** Nothing contacts the network; "offline" is a WARN, never a FAIL.

More: [docs/safety.md](docs/safety.md).

## Environments

[docs/environments.md](docs/environments.md) lists the detection signals, PRoot limitations and
Termux-specific handling.

| Environment | Support |
|---|---|
| Native Termux | First-class; fixture-tested only |
| PRoot Debian 13 | First-class; real-run here |
| Native Debian 13 | First-class; fixture-tested, plus a CI container job |
| Debian-family | Degraded |
| Other Linux | Diagnostics only |

CI is a flag, not an environment. Conflicting signals give `unknown`, never a guess.

**Termux ↔ PRoot boundary:**
- Inside a PRoot guest, jadis reports Termux binaries leaking onto the guest PATH (for example Termux's
  `pkg`).
- It never uses them for the guest: bootstrap always installs the guest's own Debian packages.
- It recognizes one SDK seen through PRoot's bind of the Termux home as one SDK, not two.

## Android development

`jadis android` checks:
- the JDK and `JAVA_HOME` consistency;
- the Gradle wrapper;
- the SDK: platforms, `android.jar`, build-tools, `aapt2`, `apksigner`, `d8`, adb and fastboot.

Android Studio is not assumed. On aarch64 (Termux/PRoot) it detects that Google's `aapt2` is x86_64 and
points to the native override (`-Pandroid.aapt2FromMavenOverride`). It reports a dangling `ANDROID_HOME`
together with the startup-file line that sets it. It does not rewrite a working, manually assembled SDK.

## Boundaries in Outer Void

| Component | Owns |
|---|---|
| jadis | *This workstation*: what it is, what it has, what is broken, safe local fixes, snapshots |
| `ax` (AXIOM) | Routing developer work to engines. If it ever adds workstation commands, they should route here rather than reimplement them |
| blux10k | Dotfiles and the `ax env` environment report. jadis does not manage dotfiles |
| BLUX | Intelligence. It may call jadis's four read-only capabilities (`.blux/`); it cannot reach repair, bootstrap or restore |
| DAT, LRC, GOD | Repository audits, repository creation, capability discovery. jadis does none of these |
| VoidForge | Android *devices*. jadis only checks that the host's adb/fastboot/SDK toolchain exists |

Not an AI agent, a package manager, a project orchestrator, a secrets vault or a flashing tool.

## Other utilities in this repository

`scripts/` holds the earlier standalone helpers:
- `github_backup` (git-crypt encrypted folder backup);
- `master_log`;
- `newproject`;
- `timelog`.

They are not part of the `jadis` CLI; see each one's README. The setup guides were rebuilt:
- [docs/termux-debian.md](docs/termux-debian.md)
- [docs/python.md](docs/python.md)
- [docs/llm-vulkan.md](docs/llm-vulkan.md)

The migration record is [docs/migration.md](docs/migration.md).

## Known limitations

- No `TERMUX_VALIDATED` or `HARDWARE_VALIDATED` evidence. Termux behavior is fixture-tested only.
- Repairs available: SSH permissions, `init.defaultBranch`, `~/.local/bin` on PATH, `ANDROID_HOME`. Other
  findings give instructions.
- No persistent probe cache: inspection must not write. `gradle --version` is slow and runs only for
  profiles that need it.
- Shadow detection reads aliases and functions in startup files and checks where core commands really
  resolve. It cannot see aliases defined only in the running interactive shell.

## License

**Outer-Void Proprietary License** (proprietary). Copyright (c) 2026 Outer-Void / Justadudeinspace (JADIS). All rights reserved. See [LICENSE](LICENSE).

Contact: outervoid.blux@gmail.com (main) · theoutervoid@outlook.com (fallback)
