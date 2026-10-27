#!/bin/bash
# github_backup.sh - Secure encrypted backups to private GitHub repository using git-crypt

###############################################################################
# GET STARTED: COMPLETE SETUP INSTRUCTIONS (see README.md for full details)
###############################################################################
# - Generate SSH key, add to agent, add to GitHub
# - Install git-crypt
# - Set environment variables: GIT_USER_NAME, GIT_USER_EMAIL, GITHUB_USER
# - Create a private GitHub repo to receive backups (or enable AUTO_CREATE_REPO)
#
# This script expects two arguments:
#   github_backup.sh folder repo_name
#
###############################################################################
# CUSTOMIZATION SECTION 1: BASIC CONFIGURATION
###############################################################################

GITHUB_USER="${GITHUB_USER:-your_github_username}"
GIT_USER_NAME="${GIT_USER_NAME:-Your Name}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-your_email@example.com}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
BRANCH_NAME="${BRANCH_NAME:-main}"

###############################################################################
# CUSTOMIZATION SECTION 2: GIT-CRYPT CONFIGURATION
###############################################################################

GIT_CRYPT_KEY_DIR="${GIT_CRYPT_KEY_DIR:-$BACKUP_DIR/.git-crypt-keys}"
AUTO_INIT_GIT_CRYPT="${AUTO_INIT_GIT_CRYPT:-1}"
GIT_CRYPT_EXPORT_KEY="${GIT_CRYPT_EXPORT_KEY:-1}"

###############################################################################
# CUSTOMIZATION SECTION 3: BACKUP RETENTION AND NAMING
###############################################################################

TIMESTAMP_FORMAT="${TIMESTAMP_FORMAT:-%Y%m%d_%H%M%S}"
MAX_LOCAL_BACKUPS="${MAX_LOCAL_BACKUPS:-3}"
INCLUDE_HOSTNAME="${INCLUDE_HOSTNAME:-1}"

###############################################################################
# CUSTOMIZATION SECTION 4: GITHUB REPOSITORY SETTINGS
###############################################################################

GIT_REMOTE="${GIT_REMOTE:-git@github.com:$GITHUB_USER/\$REPO_NAME.git}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Backup: \$FOLDER - \$TIMESTAMP}"
AUTO_CREATE_REPO="${AUTO_CREATE_REPO:-0}"

###############################################################################
# CUSTOMIZATION SECTION 5: ADVANCED FEATURES
###############################################################################
# Optional:
# GITHUB_TOKEN, NOTIFICATION_COMMAND, PRE_BACKUP_COMMAND, POST_BACKUP_COMMAND
###############################################################################

###############################################################################
# ARGUMENT HANDLING & VALIDATION
###############################################################################

if [ "$#" -ne 2 ]; then
    echo "Usage: github_backup.sh folder repo_name"
    echo "Example: github_backup.sh my_project myproject-backups"
    echo ""
    echo "Required environment variables: GIT_USER_NAME, GIT_USER_EMAIL, GITHUB_USER"
    exit 1
fi

FOLDER="$1"
REPO_NAME="$2"

# Compute GIT_REMOTE and make sure key file path can reference REPO_NAME
GIT_REMOTE="${GIT_REMOTE//\$REPO_NAME/$REPO_NAME}"
GIT_CRYPT_KEY_FILE="${GIT_CRYPT_KEY_FILE:-$GIT_CRYPT_KEY_DIR/${REPO_NAME}.key}"
COMMIT_MESSAGE="${COMMIT_MESSAGE//\$FOLDER/$FOLDER}"
TIMESTAMP=$(date +"$TIMESTAMP_FORMAT")

# Validate required environment variables are set
if [ "$GIT_USER_NAME" = "Your Name" ] || [ "$GIT_USER_EMAIL" = "your_email@example.com" ]; then
    echo "ERROR: You must set GIT_USER_NAME and GIT_USER_EMAIL environment variables"
    echo "Add to ~/.bashrc or ~/.bash_profile and run: source ~/.bashrc"
    echo "  export GIT_USER_NAME=\"Your Actual Name\""
    echo "  export GIT_USER_EMAIL=\"your_real_email@example.com\""
    exit 1
fi

if [ "$GITHUB_USER" = "your_github_username" ]; then
    echo "ERROR: You must set GITHUB_USER environment variable"
    echo "Add to ~/.bashrc or ~/.bash_profile and run: source ~/.bashrc"
    echo "  export GITHUB_USER=\"your_actual_github_username\""
    exit 1
fi

# Validate folder exists
if [ ! -d "$FOLDER" ]; then
    echo "Error: Folder '$FOLDER' does not exist or is not a directory"
    exit 1
fi

# Prepare directories
mkdir -p "$BACKUP_DIR" "$GIT_CRYPT_KEY_DIR"

###############################################################################
# TIMESTAMP AND BACKUP FOLDER NAME
###############################################################################

if [ "$INCLUDE_HOSTNAME" -eq 1 ]; then
    HOSTNAME_SHORT=$(hostname -s)
    BACKUP_FOLDER_NAME="${FOLDER}_${HOSTNAME_SHORT}_${TIMESTAMP}"
else
    BACKUP_FOLDER_NAME="${FOLDER}_${TIMESTAMP}"
fi

BACKUP_PATH="$BACKUP_DIR/$BACKUP_FOLDER_NAME"

echo "Starting backup of '$FOLDER' to GitHub repository '$REPO_NAME'"
echo "Backup folder: $BACKUP_FOLDER_NAME"
echo "Git User: $GIT_USER_NAME <$GIT_USER_EMAIL>"

###############################################################################
# PRE-BACKUP HOOK
###############################################################################

if [ -n "$PRE_BACKUP_COMMAND" ]; then
    echo "Running pre-backup command..."
    eval "$PRE_BACKUP_COMMAND"
    if [ $? -ne 0 ]; then
        echo "Warning: Pre-backup command failed, but continuing..."
    fi
fi

###############################################################################
# STEP 1: PREPARE BACKUP FOLDER
###############################################################################

echo "Step 1/6: Preparing backup folder..."
mkdir -p "$BACKUP_PATH"
cp -r "$FOLDER"/* "$BACKUP_PATH/" 2>/dev/null || cp -r "$FOLDER" "$BACKUP_PATH/"

cat > "$BACKUP_PATH/backup_metadata.txt" << EOF
Backup Information
==================
Source Folder: $FOLDER
Backup Created: $(date)
Timestamp: $TIMESTAMP
Hostname: $(hostname)
User: $USER
GitHub Repository: $REPO_NAME
Git-Crypt Encrypted: Yes
EOF

###############################################################################
# STEP 2: GITHUB REPOSITORY SETUP
###############################################################################

echo "Step 2/6: Setting up GitHub repository..."

if [ ! -d "$BACKUP_DIR/$REPO_NAME" ]; then
    echo "Cloning repository from GitHub..."
    git clone "$GIT_REMOTE" "$BACKUP_DIR/$REPO_NAME"
    if [ $? -ne 0 ]; then
        if [ "$AUTO_CREATE_REPO" -eq 1 ] && [ -n "$GITHUB_TOKEN" ]; then
            echo "Repository not found, attempting to create it..."
            curl -X POST -H "Authorization: token $GITHUB_TOKEN" \
                 -H "Accept: application/vnd.github.v3+json" \
                 https://api.github.com/user/repos \
                 -d "{\"name\":\"$REPO_NAME\",\"private\":true}" > /dev/null 2>&1
            sleep 2
            git clone "$GIT_REMOTE" "$BACKUP_DIR/$REPO_NAME"
        fi

        if [ $? -ne 0 ]; then
            echo "Error: Failed to clone repository '$REPO_NAME'"
            rm -rf "$BACKUP_PATH"
            exit 1
        fi
    fi
fi

cd "$BACKUP_DIR/$REPO_NAME" || exit 1
git config user.name "$GIT_USER_NAME"
git config user.email "$GIT_USER_EMAIL"

###############################################################################
# STEP 3: GIT-CRYPT INITIALIZATION
###############################################################################

echo "Step 3/6: Setting up git-crypt encryption..."

if ! git-crypt status > /dev/null 2>&1; then
    if [ "$AUTO_INIT_GIT_CRYPT" -eq 1 ]; then
        echo "Initializing git-crypt in repository..."
        git-crypt init

        cat > .gitattributes << EOF
* filter=git-crypt diff=git-crypt
.gitattributes !filter !diff
README.md !filter !diff
.git-crypt/ !filter !diff
EOF

        if [ "$GIT_CRYPT_EXPORT_KEY" -eq 1 ]; then
            echo "Exporting git-crypt key to $GIT_CRYPT_KEY_FILE"
            git-crypt export-key "$GIT_CRYPT_KEY_FILE"
            chmod 600 "$GIT_CRYPT_KEY_FILE"
            echo "IMPORTANT: Backup your git-crypt key safely: $GIT_CRYPT_KEY_FILE"
        fi

        git add .gitattributes
        git commit -m "Initialize git-crypt encryption"
        git push origin "$BRANCH_NAME"
    else
        echo "Error: git-crypt not initialized in repository"
        rm -rf "$BACKUP_PATH"
        exit 1
    fi
fi

###############################################################################
# STEP 4: COPY BACKUP AND COMMIT
###############################################################################

# Never commit plaintext. A fresh clone carries .gitattributes asking for the git-crypt filter, but without
# the local filter config (repository not unlocked) git silently stores files unencrypted.
if [ -z "$(git config --local --get filter.git-crypt.smudge 2>/dev/null)" ]; then
    if [ -f "$GIT_CRYPT_KEY_FILE" ]; then
        echo "Unlocking git-crypt with $GIT_CRYPT_KEY_FILE..."
        git-crypt unlock "$GIT_CRYPT_KEY_FILE" || { echo "Error: git-crypt unlock failed; nothing was committed"; rm -rf "$BACKUP_PATH"; exit 1; }
    fi
fi
if [ -z "$(git config --local --get filter.git-crypt.smudge 2>/dev/null)" ] || ! grep -q '^\* filter=git-crypt' .gitattributes 2>/dev/null; then
    echo "Error: git-crypt is not active in $BACKUP_DIR/$REPO_NAME, so the backup would be pushed unencrypted."
    echo "Unlock it first (git-crypt unlock /path/to/${REPO_NAME}.key) or set GIT_CRYPT_KEY_FILE. Nothing was committed."
    rm -rf "$BACKUP_PATH"
    exit 1
fi

echo "Step 4/6: Adding backup to repository..."
cp -r "$BACKUP_PATH" .
git add "$BACKUP_FOLDER_NAME"
git commit -m "$COMMIT_MESSAGE"

echo "Step 5/6: Pushing encrypted backup to GitHub..."
git push origin "$BRANCH_NAME"
if [ $? -ne 0 ]; then
    echo "Error: Failed to push to GitHub repository"
    rm -rf "$BACKUP_PATH"
    exit 1
fi

###############################################################################
# STEP 6: CLEANUP AND RETENTION
###############################################################################

echo "Step 6/6: Cleaning up..."
rm -rf "$BACKUP_PATH"

if [ "$MAX_LOCAL_BACKUPS" -gt 0 ]; then
    echo "Managing local backup retention (keeping $MAX_LOCAL_BACKUPS most recent)..."
    find . -maxdepth 1 -type d -name "${FOLDER}*" | sort -r | tail -n +$((MAX_LOCAL_BACKUPS + 1)) | while read -r old_backup; do
        if [ -n "$old_backup" ]; then
            echo "Removing old backup: $(basename "$old_backup")"
            git rm -r "$(basename "$old_backup")"
            git commit -m "Remove old backup: $(basename "$old_backup")"
        fi
    done
    git push origin "$BRANCH_NAME"
fi

echo ""
echo "✅ Backup completed successfully!"
echo "   Folder: $BACKUP_FOLDER_NAME"
echo "   Repository: $REPO_NAME"
echo "   Branch: $BRANCH_NAME"
echo ""
if [ "$GIT_CRYPT_EXPORT_KEY" -eq 1 ]; then
    echo "💾 Encryption key saved to: $GIT_CRYPT_KEY_FILE"
    echo "   KEEP THIS KEY SAFE - you need it to decrypt your backups!"
fi

###############################################################################
# POST-BACKUP HOOKS
###############################################################################

if [ -n "$NOTIFICATION_COMMAND" ]; then
    echo "Sending notification..."
    eval "$NOTIFICATION_COMMAND"
fi

if [ -n "$POST_BACKUP_COMMAND" ]; then
    echo "Running post-backup command..."
    eval "$POST_BACKUP_COMMAND"
fi

###############################################################################
# RESTORE INSTRUCTIONS (printed at end for convenience)
###############################################################################

echo ""
echo "Restore instructions:"
echo "1. Ensure you have the git-crypt key: $GIT_CRYPT_KEY_FILE"
echo "2. git clone $GIT_REMOTE"
echo "3. cd $REPO_NAME"
echo "4. git-crypt unlock $GIT_CRYPT_KEY_FILE"
echo ""
