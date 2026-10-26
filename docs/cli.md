# `jadis` CLI contract

Every command builds one result object. Human output and `--json` output render the same object, after the
same redaction.

## Exit codes

| Code | Name | Meaning |
|---|---|---|
| 0 | OK | Success. For `doctor`: no required check FAILed (WARN/SKIP/UNKNOWN are allowed) |
| 1 | VERIFICATION_FAILED | The machine was inspected and a required check is FAIL |
| 2 | USAGE | Bad arguments, an unknown profile or repair, an unreadable input file |
| 3 | UNSUPPORTED | The environment does not support the operation (for example apt without root or sudo) |
| 4 | INCOMPLETE | Not authorized, declined, partially applied, or interrupted |
| 70 | INTERNAL | A bug in jadis. Reported without a traceback |

## JSON

`--json` prints one object with `exit_code` plus the command's payload. The main payloads:

| Command | Format / main fields |
|---|---|
| `env` | `jadis-environment v1`: `classification`, `platform`, `android`, `termux`, `proot`, `ci`, `distribution*`, `architecture`, `kernel`, `libc`, `identity`, `shell`, `package_manager`, `memory`, `disk`, `storage`, `network`, `tools`, `android_sdk`, `java_home`, `vulkan` |
| `doctor` | `profile`, `environment`, `summary`, `checks[]` |
| `report` | `jadis-snapshot v1`: `environment` plus `doctor` |
| `repair` / `bootstrap` / `python venv` | `plans[]` (each with `mutations[]` and `reversible`), `dry_run`, `status` or `outcomes[]` |

Each entry in `checks[]` has these fields:
- `check_id`, `category`, `status`, `severity`, `summary`;
- `detected`, `expected`, `evidence[]`;
- `suggested_fix`, `auto_fixable`, `network`.

A field that could not be determined is the string `"unknown"`. Nothing is guessed.

Statuses:

| Status | Meaning |
|---|---|
| PASS | Evidence shows it is fine; a PASS without evidence is rejected by the model |
| WARN | Works, but deserves attention |
| FAIL | Broken or missing and required |
| SKIP | Does not apply here, or an optional tool is absent |
| UNKNOWN | Could not be determined |

## Commands

See `jadis --help` and `jadis <command> --help`; the README has the full command table.

- **Repair:** `jadis repair --list` shows the repair catalogue, and `jadis profiles list` shows the
  profiles.
- **Mutating commands:** `repair`, `bootstrap`, `python venv`, `restore` and `repair --rollback` accept
  `--dry-run` (or `--check` / `--plan`) and `--yes`.
- **BLUX:** `jadis blux-capability ID` is the BLUX subprocess-provider entry point. It reads a request on
  stdin and prints exactly one JSON object (BLUX ADR-0009). It serves read-only capabilities only.

## Completion

`jadis completion bash > ~/.local/share/bash-completion/completions/jadis`, or `jadis completion zsh` into
a directory on `$fpath`. The scripts are generated from the argument parser, so they cannot drift from the
commands.
