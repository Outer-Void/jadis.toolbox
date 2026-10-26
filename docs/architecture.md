# Architecture

Probes and checks read; one module writes. Every module fits on a screen.

| Module | Role |
|---|---|
| `system.py` | The only door to the machine. `RealSystem` (argv commands with timeouts and bounded output, file reads) and `FakeSystem` (fixtures). Read-only by interface |
| `environment.py` | Signals with evidence, classification (unknown on conflict), identity, storage, memory, disk, network (local route table only) |
| `probes.py` | Declarative tool table (version argv + regex), at most 2 concurrent, independent failure, origin and shadow detection; Android SDK, `JAVA_HOME`, Vulkan |
| `inspect.py` | Lazy, per-invocation inspection shared by all commands; builds the fingerprint |
| `profiles.py` + `profiles/*.json` | Declarative profiles: requirements, minimum versions, checks, environments, package mappings, `extends`; schema validation |
| `doctor.py` | Check registry; results carry evidence; scoped by environment once it is known |
| `mutations.py` | Plans, authorization, executor, backups, journal, rollback. **The only writer** |
| `repair.py` / `bootstrap.py` | Turn an inspection into plans, never into writes |
| `report.py`, `backup.py` | Snapshots and diffs; credential-free config backups |
| `redact.py` | One redactor for every output |
| `blux_capability.py` | Optional read-only BLUX subprocess provider |
| `cli.py` | argparse tree. Each command returns `(exit code, payload, human lines)`, rendered as JSON or text |

There are no third-party runtime dependencies, so the same wheel installs in Termux, PRoot Debian and Debian.
