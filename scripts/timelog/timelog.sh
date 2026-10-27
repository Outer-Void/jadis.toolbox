#!/bin/bash
# timelog.sh - Enhanced time tracking script

###############################################################################
# CUSTOMIZATION SECTION 1: LOCATION CONFIGURATION
###############################################################################

CONFIG_DIR="${TIMELOG_CONFIG:-$HOME/.config/timelog}"
LOG_DIR="${TIMELOG_DIR:-$HOME/timelogs}"
LOG_FILE="${LOG_DIR}/timelog.csv"
CONFIG_FILE="${CONFIG_DIR}/timelog.conf"

###############################################################################
# CUSTOMIZATION SECTION 2: DIRECTORY SETUP
###############################################################################

mkdir -p "$CONFIG_DIR" "$LOG_DIR"

###############################################################################
# CUSTOMIZATION SECTION 3: CONFIGURATION LOADING
###############################################################################

if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
fi

###############################################################################
# CUSTOMIZATION SECTION 4: DATE/TIME FORMATS
###############################################################################

: "${TIMEZONE:="$(date +%Z)"}"
: "${DATE_FORMAT:="%Y-%m-%d"}"
: "${TIME_FORMAT:="%H:%M:%S"}"
: "${DATETIME_FORMAT:="%Y-%m-%d %H:%M:%S %Z"}"

# The log is CSV: commas in free text would shift every later column, so they are replaced.
csv_safe() { printf '%s' "${1//,/;}"; }

###############################################################################
# MAIN SCRIPT LOGIC
###############################################################################

case "$1" in
  start)
    if [[ -z "$2" ]]; then
        echo "Error: Project name required"
        echo "Usage: timelog.sh start project-name [additional-info]"
        exit 1
    fi
    
    if [[ -f "${CONFIG_DIR}/current_project" ]]; then
        current_project=$(cat "${CONFIG_DIR}/current_project")
        echo "Error: Project '$current_project' is already running. Stop it first."
        exit 1
    fi

    project=$(csv_safe "$2")
    echo "$project" > "${CONFIG_DIR}/current_project"
    date +%s > "${CONFIG_DIR}/start_time"

    timestamp=$(date +"$DATETIME_FORMAT")
    additional_info=$(csv_safe "${3:-}")
    session_id=$(date +%s%N | md5sum | head -c 8)
    
    echo "$(date +"$DATE_FORMAT"),$project,START,$(date +"$TIME_FORMAT"),$timestamp,$TIMEZONE,$session_id,$additional_info,$USER" >> "$LOG_FILE"
    echo "Started '$project' at $(date +"$TIME_FORMAT") (Session: $session_id)"
    ;;
    
  stop)
    if [[ ! -f "${CONFIG_DIR}/current_project" ]]; then
        echo "Error: No project currently running"
        exit 1
    fi

    project=$(cat "${CONFIG_DIR}/current_project")
    start_time=$(cat "${CONFIG_DIR}/start_time")
    current_time=$(date +%s)
    duration=$((current_time - start_time))
    
    hours=$((duration / 3600))
    minutes=$(( (duration % 3600) / 60 ))
    seconds=$((duration % 60))
    duration_str=$(printf "%02d:%02d:%02d" "$hours" "$minutes" "$seconds")
    
    session_id=$(grep ",$project,START" "$LOG_FILE" | tail -1 | cut -d, -f7)
    timestamp=$(date +"$DATETIME_FORMAT")
    additional_info=$(csv_safe "${2:-}")

    echo "$(date +"$DATE_FORMAT"),$project,STOP,$(date +"$TIME_FORMAT"),$timestamp,$TIMEZONE,$session_id,$additional_info,$USER,$duration_str" >> "$LOG_FILE"
    
    rm "${CONFIG_DIR}/current_project" "${CONFIG_DIR}/start_time"
    echo "Stopped '$project' at $(date +"$TIME_FORMAT")"
    echo "Duration: $duration_str"
    ;;
    
  status)
    if [[ -f "${CONFIG_DIR}/current_project" ]]; then
        project=$(cat "${CONFIG_DIR}/current_project")
        start_time=$(cat "${CONFIG_DIR}/start_time")
        current_time=$(date +%s)
        duration=$((current_time - start_time))
        hours=$((duration / 3600))
        minutes=$(( (duration % 3600) / 60 ))
        seconds=$((duration % 60))
        echo "Current project: $project"
        echo "Started: $(date -d "@$start_time" +"$DATETIME_FORMAT")"
        echo "Duration: $(printf "%02d:%02d:%02d" "$hours" "$minutes" "$seconds")"
    else
        echo "No project currently running"
    fi
    ;;
    
  invoice)
    if [[ -z "$2" ]]; then
        echo "Error: Project name required"
        echo "Usage: timelog.sh invoice project-name [output-file]"
        exit 1
    fi
    
    [[ -f "$LOG_FILE" ]] || { echo "Error: no time log at $LOG_FILE"; exit 1; }
    output_file="${3:-${TMPDIR:-/tmp}/invoice-$2-$(date +%Y%m%d).txt}"

    set -o pipefail
    if ! {
        echo "Time Invoice for: $2"
        echo "Generated: $(date +"$DATETIME_FORMAT")"
        echo "User: $USER"
        echo "=========================================="
        echo ""
        echo "Session Log:"
        echo "------------"
        awk -F, -v project="$2" '$2==project {printf "%-10s %-8s %-12s | %s\n", $1, $4, $3, ($8==""?"-":$8)}' "$LOG_FILE"
        
        echo ""
        echo "Session Summary:"
        echo "----------------"
        # Portable awk (mawk, busybox, gawk): totals come from the duration recorded on each STOP row.
        awk -F, -v project="$2" '
        $2==project && $3=="STOP" && $10 ~ /^[0-9]+:[0-9][0-9]:[0-9][0-9]$/ {
            split($10, t, ":"); total += t[1]*3600 + t[2]*60 + t[3]; sessions++
        }
        END {
            h=int(total/3600); m=int((total%3600)/60); s=total%60
            printf "Total Sessions: %d\nTotal Time: %02d:%02d:%02d\nTotal Hours: %.2f\n", sessions,h,m,s,total/3600
        }' "$LOG_FILE"
    } > "$output_file"; then
        echo "Error: could not write the invoice to $output_file" >&2
        exit 1
    fi
    echo "Invoice written to: $output_file"
    ;;
    
  config)
    echo "Current configuration:"
    echo "  Config directory: $CONFIG_DIR"
    echo "  Log directory: $LOG_DIR"
    echo "  Log file: $LOG_FILE"
    echo "  Timezone: $TIMEZONE"
    echo "  Date format: $DATE_FORMAT"
    echo "  Time format: $TIME_FORMAT"
    echo ""
    echo "To customize, set environment variables:"
    echo "  TIMELOG_CONFIG, TIMELOG_DIR"
    echo "Or edit config file: $CONFIG_FILE"
    ;;
    
  ""|help|-h|--help)
    echo "Enhanced Time Logging System"
    echo "Usage: timelog.sh {start|stop|status|invoice|config} [project-name] [info]"
    echo ""
    echo "Commands:"
    echo "  start project [info]  - Start tracking time"
    echo "  stop [info]           - Stop tracking current project"
    echo "  status                - Show current tracking status"
    echo "  invoice project [out] - Generate invoice for project"
    echo "  config                - Show current configuration"
    ;;

  *)
    echo "Unknown command: $1 (see: timelog.sh help)" >&2
    exit 2
    ;;
esac
