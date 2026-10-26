# Safety model

## Inspection is read-only

`env`, `info`, `doctor` and every doctor view, `report` (without `--out`), `repair --check/--dry-run`,
`bootstrap --plan/--dry-run`, `restore --dry-run` and the BLUX capabilities **change nothing**:
- Checks receive only an inspection object, which has no write API.
- `tests/test_mutations.py::test_doctor_env_and_report_perform_zero_mutations` runs them against a real
  temporary home and compares every file's hash and mode before and after.
- There is deliberately no on-disk probe cache, because a cache would be a write.

## Mutation barrier (`jadis.mutations`)

`inspect → plan → show → authorize → apply → verify → journal`:

1. A **plan** lists every mutation (`chmod`, `managed_block`, `mkdir`, `run`) with its exact target and
   whether it is reversible.
2. **Authorization** is `--yes`, or `y` typed at an interactive terminal. A non-interactive run without
   `--yes` changes nothing and exits 4.
3. **Files** are backed up before writing (`$XDG_STATE_HOME/jadis/backups/<run>/`). Shell files are only
   changed inside `# >>> jadis managed: NAME >>>` … `# <<< jadis managed: NAME <<<`; everything outside the
   block stays byte-identical.
4. **Commands** run as argv, never through a shell, with timeouts.
5. **Journal:** every applied mutation is a line in `$XDG_STATE_HOME/jadis/journal.jsonl`. A failure
   mid-plan records what was applied and stops; it never hides partial work.
6. **Rollback:** `jadis repair --rollback RUN` restores modes, restores files from backup (or removes the
   managed block from files jadis created) and runs recorded undo commands. Package installs are not
   automatically reversible, and the plan says so.

Repairs are idempotent: once a repair has been applied, it plans nothing on the next run.

Never touched:
- your Git identity;
- key contents, since only file modes are read;
- package source lists;
- the Android SDK layout;
- GPU drivers;
- global Python packages.

## Secrets

- The environment is never dumped. Variable names that look sensitive (TOKEN, SECRET, PASSWORD, API_KEY,
  PRIVATE, CREDENTIAL, SIGNING, KEYSTORE …) mark their *values* as known secrets, redacted wherever they
  appear.
- Token-shaped strings are replaced in every human and JSON output, including tool output: GitHub
  (`ghp_`, `github_pat_`), OpenAI/Anthropic-style `sk-…`, AWS `AKIA…`, Slack `xox?-`, Google `AIza…`, JWTs,
  bearer/token assignments, URL credentials and private-key blocks.
- `$HOME` is printed as `~`.
- `backup` skips `.git-credentials`, `.netrc`, `~/.ssh` and any file whose content looks like a credential.
- Nothing is ever uploaded. No downloaded script is executed. jadis has no `curl | sh` path.

Tests: `tests/test_redaction.py` injects fake keys and tokens through environment values, tool output, git
config and shell files, then asserts none appear in any of eight report variants. The patterns are also used
by `tools/repo_hygiene.py` in CI to keep real secrets out of the repository.

## Offline

Doctor and env never open a network connection. `network.local` reads only the local route table. Being
offline is a WARN and never fails the doctor.

## BLUX

The four BLUX capabilities are read-only and share the CLI's engine. Repair, bootstrap, venv and restore
have no BLUX capability, so BLUX cannot reach a mutation. A request for any other capability id is refused.
