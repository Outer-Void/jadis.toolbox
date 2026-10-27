# GitHub Backup — Encrypted backups with git-crypt

A focused, pragmatic script to copy a local folder into a private GitHub repository and transparently encrypt it with `git-crypt`.  
Gentle warning: encryption keys are precious — back them up. This README is your map.

---

## Quick summary

- Copies a folder into a backup folder (timestamped)
- Initializes `git-crypt` in the repo (optional)
- Commits and pushes encrypted backup to a private GitHub repository
- Manages retention of old backups inside the repository
- Optional hooks for pre/post backup and notifications

---

## Prerequisites (one-time)

1. SSH keys & GitHub access
   ```bash
   ssh-keygen -t ed25519 -C "you@example.com"
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519
   cat ~/.ssh/id_ed25519.pub  # add to GitHub -> Settings -> SSH and GPG keys
   ```
2. Install required tools
```
git

git-crypt (sudo apt install git-crypt or brew install git-crypt)
```


3. Required environment variables (add to `~/.bashrc`):
```
export GIT_USER_NAME="Your Actual Name"
export GIT_USER_EMAIL="your_real_email@example.com"
export GITHUB_USER="your_actual_github_username"
```

4. Create a private GitHub repo (or enable `AUTO_CREATE_REPO` and supply `GITHUB_TOKEN`).




---

## Configuration variables (defaults shown)

You can set these in your environment or edit before running:
```
GITHUB_USER=your_github_username
GIT_USER_NAME="Your Name"
GIT_USER_EMAIL="you@example.com"
BACKUP_DIR=~/backups
BRANCH_NAME=main
GIT_CRYPT_KEY_DIR=~/backups/.git-crypt-keys
TIMESTAMP_FORMAT="%Y%m%d_%H%M%S"
MAX_LOCAL_BACKUPS=3
INCLUDE_HOSTNAME=1
GIT_REMOTE="git@github.com:<GITHUB_USER>/<REPO_NAME>.git"
COMMIT_MESSAGE="Backup: <FOLDER> - <TIMESTAMP>"
AUTO_CREATE_REPO=0
AUTO_INIT_GIT_CRYPT=1
GIT_CRYPT_EXPORT_KEY=1
```
Security note: `GIT_CRYPT_KEY_DIR` holds encryption keys. Keep it safe and backed up offline.


---

## Plaintext guard

Before copying anything into the repository, the script checks that git-crypt is active there. A fresh clone
(for example on a second device) carries `.gitattributes` asking for encryption but is not unlocked, and git
would then store files unencrypted. If the repository is locked, the script unlocks it with
`$GIT_CRYPT_KEY_DIR/<repo>.key` (or `GIT_CRYPT_KEY_FILE`) when that file exists; otherwise it stops and commits
nothing. `tests/test_scripts.py` checks that a locked clone never receives a commit.

## Usage
```
Make the script executable:

chmod +x github_backup.sh

Run the backup:

./github_backup.sh /path/to/folder my-backup-repo

Example:

./github_backup.sh ~/Documents mydocs-backups

If you want the script to auto-create the repo (advanced), set:

export AUTO_CREATE_REPO=1
export GITHUB_TOKEN="ghp_your_token_here"  # secure this token!
```

---

## Hooks & advanced options
```
PRE_BACKUP_COMMAND — run before copying (e.g., database dump)

POST_BACKUP_COMMAND — run after backup completes

NOTIFICATION_COMMAND — notify via notify-send, curl (webhook), mail, etc.

AUTO_INIT_GIT_CRYPT=0 — disable automatic git-crypt init if you prefer manual control

GIT_CRYPT_EXPORT_KEY=1 — export and save the symmetric key used by git-crypt (recommended)
```


---

## Retention behavior

The script keeps the newest `MAX_LOCAL_BACKUPS` copies inside the repository and removes older ones from the repo (commits the removals and pushes them). Set `MAX_LOCAL_BACKUPS=0` to disable pruning.


---

## Restore instructions

To restore a backup:

1. Ensure you have the `git-crypt` key (example location printed by the script):

`$GIT_CRYPT_KEY_DIR/<repo_name>.key`


2. Clone the repo:
```
git clone git@github.com:YOUR_USER/REPO_NAME.git
cd REPO_NAME
```

3. Unlock:
```
git-crypt unlock /path/to/<repo_name>.key
```

4. The backup folders will now be decrypted and readable.




---

## Termux / Android notes

Termux users may need to compile or build `git-crypt` manually. Install `git` and `gnupg` first:
```
pkg install git gnupg
# Follow git-crypt repo instructions to build/install if packages aren't available
```

---

## Examples

Basic backup:

`./github_backup.sh /var/www myserver-backups`

Backup with custom envs:
```
export BACKUP_DIR="$HOME/backups"; export MAX_LOCAL_BACKUPS=5
./github_backup.sh ~/projects/projectX projectX-backup
```

---

## Safety & best practices

Always securely store the exported `git-crypt` key. Without it, your backups are unrecoverable.

Use private repositories for sensitive data.

Rotate access tokens/SSH keys if a machine is compromised.

Consider storing the `git-crypt` key in a hardware-backed secret manager for extra safety.



---

## Philosophy (short)

Backups are an act of care. Encrypt them, store the keys with reverence, and let your future self breathe easier.


---
