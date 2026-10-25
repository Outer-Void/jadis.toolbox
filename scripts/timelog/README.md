# 🕒 TimeLog — Enhanced CLI Time Tracker

A simple, powerful Bash-based time tracking system with session linking, duration calculation, and invoicing features.  
Customizable via config files or environment variables — designed for developers, freelancers, and tinkerers.

---

## 🚀 Quick Start

```bash
# Clone or copy script
chmod +x timelog.sh

# Start tracking a project
./timelog.sh start "Project Alpha" "Initial setup"

# Stop tracking
./timelog.sh stop "Wrapped up task A"

# Check current status
./timelog.sh status

# Generate an invoice
./timelog.sh invoice "Project Alpha" ~/invoice.txt

# View configuration
./timelog.sh config
```

---

## ⚙️ Configuration

Option 1 — Environment Variables (Recommended)

Add to your shell profile (`~/.bashrc` or `~/.bash_profile`):
```bash
export TIMELOG_CONFIG="$HOME/.my_custom_timelog_config"
export TIMELOG_DIR="$HOME/Documents/my_timelogs"
```
Option 2 — Config File

Create a config file at:
```bash
~/.config/timelog/timelog.conf
```
With contents such as:
```bash
TIMEZONE="EST"
DATE_FORMAT="%m/%d/%Y"
TIME_FORMAT="%I:%M:%S %p"
```

---

## 🧩 Customization

Date & Time Formats

`DATE_FORMAT="%Y-%m-%d"` → ISO format

`TIME_FORMAT="%H:%M:%S"` → 24-hour clock

Change to your liking (see man date)


Session ID

Default: 8-character MD5 hash

You can modify generation method in the start section, e.g.:

`session_id=$(uuidgen)`


Invoice Generation

Default output: `/tmp/invoice-project-YYYYMMDD.txt`

Add cost calculations easily within the AWK summary section.



---

## 📦 File Locations

Purpose	Default Path

Config directory	`~/.config/timelog`
Log directory	`~/timelogs`
Main log file	`~/timelogs/timelog.csv`
Config file	`~/.config/timelog/timelog.conf`



---

## 📘 Log Format

CSV columns:

Date, Project, Action, Time, Full Timestamp, Timezone, SessionID, Info, User, Duration

Example:
```
2025-10-17,Project Alpha,START,14:02:00,2025-10-17 14:02:00 UTC,UTC,9d8a2bce,Initial setup,user
2025-10-17,Project Alpha,STOP,16:10:00,2025-10-17 16:10:00 UTC,UTC,9d8a2bce,Task complete,user,02:08:00
```

---

## 💡 Tips

Use short project names (no spaces) for cleaner logs.

For long-term usage, back up `~/timelogs/timelog.csv`.

Use `grep` or `awk` to filter project history.



---

## 🧠 License

Proprietary: part of jadis.toolbox under the Outer-Void Proprietary License (see the repository `LICENSE`).
Copies obtained before 2026-10-25 remain available under the MIT License they were published with.

> “Track your time like your art — precisely, purposefully, and with heart.”



---
