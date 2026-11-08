# MASTER_LOG Bash Script

> - No Root Required
> - Use with `termux-widget` or manually

---

## Function

Takes snapshots of Logs:
- tree (Dir tree snapshot)
- logcat (Recent logcat snapshot)
- termux-battery-status (Battery status snapshot)
- ps (Active processes snapshot)
- ping (Network snapshot; only with `MASTER_LOG_PING=1`)

---

## Quick-start

> **Privacy (OV-54, owner decision 2026-11-07):** the snapshots include your home-directory listing, `logcat`
> and `ps aux` (process command lines can contain tokens), so by default they go to private, owner-only storage:
> `~/.local/state/jadis/master_log/logs`. Nothing contacts the network unless you ask.
> - `MASTER_LOG_DIR=$HOME/storage/shared` writes to `~/storage/shared/logs` (`/sdcard/logs`) as before; any app
>   with storage permission can read it.
> - `MASTER_LOG_PING=1` adds the `ping` step, which contacts 8.8.8.8.
>
> For the widget, put the variables in the shortcut, e.g. a `~/.shortcuts/master-log-shared.sh` containing
> `MASTER_LOG_DIR=$HOME/storage/shared MASTER_LOG_PING=1 exec bash ~/.shortcuts/take-master_log.sh`.

1. Install Deps
```bash
pkg update && pkg upgrade -y
pkg install bash coreutils findutils grep gawk tree iputils procps android-tools termux-api -y
termux-setup-storage
```

2. Clone REPO/master_log folder
```bash
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/Justadudeinspace/jadis.toolbox.git
cd jadis.toolbox
git sparse-checkout init --cone
git sparse-checkout set scripts/master_log
```

- or Download Zip
```
Click Code → Download ZIP

Unzip locally.
```
> Quick

3. Move `take-master_log.sh` to `~/.shortcuts`
```bash
# Make sure the destination folder exists
mkdir -p ~/.shortcuts

# Move the script and make it executable
mv ~/jadis.toolbox/scripts/master_log/take-master_log.sh ~/.shortcuts/
chmod +x ~/.shortcuts/take-master_log.sh
```

4. Execute script
```bash
# From working Dir
./take-master_log.sh

# or from any Dir
bash ~/.shortcuts/take-master_log.sh

# or refresh termux-widget and one tap
```

5. Creates individual log snapshots

Local (default, private):
`/data/data/com.termux/files/home/.local/state/jadis/master_log/logs`

With `MASTER_LOG_DIR=$HOME/storage/shared`:
`/data/data/com.termux/files/home/storage/shared/logs`

Via (Time/Date Stamped):
```bash
 master-log-battery.json
 master-log-logcat.log
 master-log-ping.log
 master-log-ps.log
 master-log-tree.log
 master.log
```

---

exit 0
