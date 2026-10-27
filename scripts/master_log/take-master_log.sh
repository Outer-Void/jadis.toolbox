#!/data/data/com.termux/files/usr/bin/bash
# - Termux MASTER_LOG Bash Script by: ~JADIS
# One-tap snapshot (robust): $HOME tree + system logs
# Place in ~/.shortcuts and add to Termux:Widget
#  - No Root Required 
#
# Behavior:
#  - prefer emulated/0 if available, else internal shared (/sdcard)
#  - create per-snapshot files and append summary into master.log
#  - gracefully handle missing commands, permission denials, or syscalls rejected.
#
# Notes:
#  - termux-battery-status requires termux-api package & permission.
#  - Make sure all deps installed from repo README.md

# Do not use `set -e` here so single command failures don't abort the whole widget run.
set -uo pipefail

ROOT="$HOME"
SNAP_PREFIX="master-log"
MASTER_LOG="master.log"

# storage target detection (MASTER_LOG_DIR overrides it; the default is shared storage, readable by
# other apps that hold storage permission)
if [ -n "${MASTER_LOG_DIR:-}" ]; then
  BASEDIR="$MASTER_LOG_DIR"
elif [ -d "$HOME/storage/emulated/0" ]; then
  BASEDIR="$HOME/storage/emulated/0"
elif [ -d "$HOME/storage/shared" ]; then
  BASEDIR="$HOME/storage/shared"
else
  BASEDIR="/sdcard"
fi

LOGDIR="$BASEDIR/logs"
mkdir -p "$LOGDIR"

STAMP_FULL="$(date '+%Y-%m-%d %H:%M:%S')"
STAMP_FILE="$(date '+%Y%m%d-%H%M%S')"
MASTERLOG_PATH="$LOGDIR/$MASTER_LOG"

# portable file-size helper
_file_size() {
  local f="$1"
  if [ -f "$f" ]; then
    if stat -c%s "$f" >/dev/null 2>&1; then
      stat -c%s "$f" 2>/dev/null || echo "unknown"
    else
      wc -c <"$f" 2>/dev/null || echo "unknown"
    fi
  else
    echo "0"
  fi
}

# safe runner: runs a string command via bash -c, captures output, logs status
# args: name outfile cmdstring
_run_snapshot() {
  local name="$1"; shift
  local outfile="$1"; shift
  local cmdstr="$*"

  # write run-line to master log
  echo "[${STAMP_FULL}] Running: ${cmdstr}" >> "$MASTERLOG_PATH"

  # does the executable exist? try to extract the first token as command
  local prog
  prog="$(printf '%s' "$cmdstr" | awk '{print $1}' 2>/dev/null || true)"
  if [ -z "$prog" ]; then
    echo "[WARN] empty command for $name" >> "$MASTERLOG_PATH"
    printf "empty command\n" >"$outfile"
    return
  fi

  if ! command -v "$prog" >/dev/null 2>&1; then
    echo "[MISSING] command '$prog' not found; skipping $name" >> "$MASTERLOG_PATH"
    printf "Command '%s' not found\n" "$prog" >"$outfile"
    return
  fi

  # run it via bash -c so that complex commands are supported
  # capture stderr+stdout in the outfile and capture exit code
  # dmesg (removed for no root) support added
  bash -c "$cmdstr" >"$outfile" 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then
    echo "[OK] $name -> $(basename "$outfile") (size $(_file_size "$outfile") bytes)" >> "$MASTERLOG_PATH"
  else
    # Detect common kernel refusal "Bad system call" by inspecting the file or rc
    if grep -qi "Bad system call" "$outfile" >/dev/null 2>&1; then
      echo "[FAIL] $name failed: Bad system call (likely denied by kernel/SELinux). See $outfile" >> "$MASTERLOG_PATH"
    else
      echo "[WARN] $name exited rc=$rc; see $outfile" >> "$MASTERLOG_PATH"
    fi
  fi
}

# header
cat >> "$MASTERLOG_PATH" <<EOF

===============================================
[${STAMP_FULL}] Snapshot Start: ${ROOT}
-----------------------------------------------
EOF

# 1) tree snapshot (or fallback)
SNAP_TREE="$LOGDIR/${SNAP_PREFIX}-tree-${STAMP_FILE}.log"
if command -v tree >/dev/null 2>&1; then
  # try using --timefmt if supported
  if tree --help 2>&1 | grep -q -- '--timefmt' >/dev/null 2>&1; then
    _run_snapshot "tree" "$SNAP_TREE" "tree -du --timefmt='%Y-%m-%d %H:%M:%S' --device '$ROOT'"
  else
    _run_snapshot "tree" "$SNAP_TREE" "tree -du '$ROOT'"
  fi
else
  # portable fallback: find + ls -ld for each entry (safe)
  _run_snapshot "tree-fallback" "$SNAP_TREE" "bash -c \"find '$ROOT' -print0 2>/dev/null | xargs -0 -I{} sh -c 'ls -ld -- \"{}\" 2>/dev/null || printf \"%s\\n\" \"{}\"'\""
fi

# 2) logcat
SNAP_LOGCAT="$LOGDIR/${SNAP_PREFIX}-logcat-${STAMP_FILE}.log"
_run_snapshot "logcat" "$SNAP_LOGCAT" "logcat -d -v time"

# 3) termux battery (termux-api required)
SNAP_BATT="$LOGDIR/${SNAP_PREFIX}-battery-${STAMP_FILE}.json"
_run_snapshot "battery" "$SNAP_BATT" "termux-battery-status"

# 4) processes (ps)
SNAP_PS="$LOGDIR/${SNAP_PREFIX}-ps-${STAMP_FILE}.log"
# choose safest ps invocation
if command -v ps >/dev/null 2>&1; then
  if ps aux >/dev/null 2>&1; then
    _run_snapshot "ps" "$SNAP_PS" "ps aux"
  else
    _run_snapshot "ps" "$SNAP_PS" "ps -ef"
  fi
else
  _run_snapshot "ps" "$SNAP_PS" "ps"
fi

# 5) ping (network)
SNAP_NET="$LOGDIR/${SNAP_PREFIX}-ping-${STAMP_FILE}.log"
# use numeric IP to avoid DNS
_run_snapshot "ping" "$SNAP_NET" "ping -c 5 8.8.8.8"

# footer summary
cat >> "$MASTERLOG_PATH" <<EOF
-----------------------------------------------
[${STAMP_FULL}] Snapshots created (directory: ${LOGDIR})
Files:
 - $(basename "$SNAP_TREE")
 - $(basename "$SNAP_LOGCAT")
 - $(basename "$SNAP_BATT")
 - $(basename "$SNAP_PS")
 - $(basename "$SNAP_NET")
===============================================
EOF

# toast if available
if command -v termux-toast >/dev/null 2>&1; then
  if [ -n "$SNAP_TREE" ]; then
    termux-toast "Snapshot done → $(basename "$SNAP_TREE") + system logs"
  else
    termux-toast "Snapshot done → (no snapshot tree) + system logs"
  fi
else
  # audible bell for environments without toast
  printf '\a'
fi

exit 0
