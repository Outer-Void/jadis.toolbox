# Migration record (2026-10-26)

The repository changed from setup notes plus four scripts into the JADIS Toolbox product. Each piece of
existing content was classified:

| Content | Class | Outcome |
|---|---|---|
| `README.md` (BLUX operating checklist) | HISTORICAL | Moved unchanged to [personal/operating-checklist.md](personal/operating-checklist.md); the README now describes the product |
| `docs/termux-debian.md` | UPDATE + MIGRATE_TO_TOOLING | Rewritten as [termux-debian.md](termux-debian.md). Personal username and email became placeholders; package and diagnostic steps became `jadis bootstrap`/`doctor`/`repair`; `curl \| sh` installers replaced by clone-and-read; the empty SSH section filled in |
| `docs/termux-venv.md` | MIGRATE_TO_TOOLING | Replaced by `jadis python` and [python.md](python.md). The `echo … >> ~/.bashrc` advice was dropped (jadis edits only marked blocks) |
| `docs/termux-llm-vulcan.md` | REMOVE_AS_INCORRECT | Deleted (it is in git history) and replaced by [llm-vulkan.md](llm-vulkan.md) and `jadis llm` / `jadis vulkan` |
| `scripts/github_backup`, `master_log`, `newproject`, `timelog` | CURRENT | Unchanged standalone utilities, outside the `jadis` CLI. Folding them in is Stage 33 work |

The deleted Vulkan document had these defects:
- duplicated, corrupted tails ("References" repeated, with mangled link text);
- a GPU-driver `.deb` taken from a third-party tutorial repository, linked as `-5` but installed as `-7`;
- the `vulcan.dep` typo;
- `--host 0.0.0.0` presented as the way to "call remotely";
- a hard-coded `/system/lib64/libvulkan.so` presented as a general solution.

## Deviations from the overhaul brief, and why

- **No persistent probe cache.** The hard gate requires `env` and `doctor` to make zero mutations. Slow
  probes run only when a profile needs them.
- **Commands consolidated.** No `status` (same as `info`); no `install`, `update` or `clean` (`bootstrap`
  and `repair` cover them). `shell`, `git`, `ssh`, `java`, `android`, `debian` and `llm` are doctor views.
  `repair --list` and `--rollback` are flags rather than subcommands.
- **The repair catalogue is small** (4 repairs). Every other finding gives instructions rather than an
  unproven automatic fix.
