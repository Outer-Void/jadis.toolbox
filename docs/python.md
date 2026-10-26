# Python on Termux and Debian

Replaces `termux-venv.md`. Its steps are now `jadis python` (see [migration.md](migration.md)).

```sh
jadis python status    # interpreter, pip, project .venv, active venv
jadis python doctor    # venv/ensurepip availability, externally-managed Python, broken .venv
jadis python venv      # plan a project-local .venv (asks before creating; --dry-run to just show it)
source .venv/bin/activate
python -m pip install -r requirements.txt   # inside the venv only
```

Getting `venv` and `ensurepip`:

| Environment | Command |
|---|---|
| Termux | `pkg install python` provides both; `pip` comes with `python-pip` |
| Debian | `sudo apt-get install python3-venv python3-pip` |

- Debian 12+ marks the system Python **externally managed** (PEP 668), so `pip install` outside a venv is
  refused. Do not override that with `--break-system-packages` or `sudo pip`; jadis never modifies global
  packages.
- A broken `.venv` (moved directory, removed interpreter) is reported by `jadis python doctor`. Recreate it
  with `jadis python venv --recreate`.
- For a convenience alias, put it in your own shell config. Do not append blindly with `echo … >> ~/.bashrc`.
