# NewProject — Project bootstrapper

A gentle, opinionated script to seed new projects. It creates folders, templates, initializes `git`, writes a license, and optionally creates a GitHub repository. Keep it simple, keep it adaptable — like planting trees for future forests.

## Features
- Create project scaffold in `PROJECTS_DIR` (default: `~/projects`)
- `README`, `.gitignore`, `LICENSE` creation (proprietary by default; MIT and others with `-l`)
- Language-specific templates (`python`, `node`, `bash`, `web`)
- Git initialization and per-repo `git user/email`
- Optional GitHub repo creation via `gh` CLI
- Initial commit (configurable)

## Install
Copy `newproject.sh` into a folder in your PATH or keep it local. Make executable:

```bash
chmod +x newproject.sh
```

## Quickstart
```bash
# Basic
./newproject.sh my-awesome-project

# With description and type
./newproject.sh -d "A machine learning project" -t python ml-project

# Create GitHub repo and use custom user/email
./newproject.sh -g -u "Jane Doe" -e "jane@example.com" awesome-repo

Options

-d, --description  Project description

-l, --license      License (Proprietary [default], MIT, GPL-3.0, Apache-2.0, BSD-3-Clause, None); unknown names are refused

-t, --type         Project type: python, node, bash, web, or general

-u, --user         Git username (for this repo)

-e, --email        Git email (for this repo)

-g, --github       Create GitHub repo (requires gh)

-n, --no-commit    Skip initial commit

-h, --help         Show help
```

## Environment variables (defaults)

`PROJECTS_DIR` — directory where new projects are created (default `~/projects`)

`DEFAULT_GIT_USER` — default `git username`

`DEFAULT_GIT_EMAIL` — default `git email`

`DEFAULT_LICENSE` — default license (`Proprietary`)

`DEFAULT_COPYRIGHT_HOLDER` — copyright holder in `LICENSE` (default `Outer-Void / Justadudeinspace (JADIS)`)

`DEFAULT_INIT_COMMIT` — 1 to auto commit, 0 to skip

`CREATE_GITHUB_REPO` — 1 to try GitHub creation automatically


Add them to `~/.bashrc` / `~/.bash_profile` to persist:
```bash
export PROJECTS_DIR="$HOME/projects"
export DEFAULT_GIT_USER="Your Name"
export DEFAULT_GIT_EMAIL="you@host.example"
export DEFAULT_LICENSE="MIT"
```

## Templates & Customization

`README_TEMPLATE`, `GITIGNORE_TEMPLATE`, and `MIT_LICENSE` are defined inside the script. Edit them to reflect your style.

Language templates are arrays in the script (`PYTHON_FILES`, `NODEJS_FILES`, `BASH_FILES`) — add or change entries to tailor initial files.

The `create_language_files` function builds language-specific structure; extend it for more languages.


## GitHub integration

Requires GitHub CLI (`gh`) and authenticated session (`gh auth login`).

When enabled (`-g`), script will attempt to create a private repository and push.


## Examples
```
# Create a simple project
./newproject.sh todo-app

# Create a Python project with description and license
./newproject.sh -d "Data pipeline for analytics" -t python -l Apache-2.0 analytics-pipeline

# Use a different git identity for the new repo
./newproject.sh -u "John Doe" -e "john@company.com" company-project
```

## Philosophy (short & soft)

Start small. Start clear. One commit seeds many possibilities. This script is scaffolding — a humble companion for the first step.

## License

Use freely. Change freely. This file is offered without warranty — like everything you build, it grows in your hands.

---
