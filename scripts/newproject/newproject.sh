#!/bin/bash
# newproject.sh - Advanced Project Initialization Script
# Create a new project with templates, git init, license, and optional GitHub creation.

###############################################################################
# DEFAULT CONFIGURATION (can be overridden via environment variables)
###############################################################################
PROJECTS_DIR="${PROJECTS_DIR:-$HOME/projects}"
DEFAULT_GIT_USER="${DEFAULT_GIT_USER:-${USER:-Project Developer}}"
DEFAULT_GIT_EMAIL="${DEFAULT_GIT_EMAIL:-${USER:-dev}@localhost}"
DEFAULT_LICENSE="${DEFAULT_LICENSE:-MIT}"
DEFAULT_INIT_COMMIT="${DEFAULT_INIT_COMMIT:-1}"
CREATE_GITHUB_REPO="${CREATE_GITHUB_REPO:-0}"

###############################################################################
# TEMPLATES (customize content between EOF markers)
###############################################################################

README_TEMPLATE=$(cat << 'EOF'
# ${PROJECT_NAME}

## Description
${PROJECT_DESCRIPTION}

## Project Structure

${PROJECT_TREE}

## Installation
\`\`\`bash
# Add installation instructions here
\`\`\`

## Usage
\`\`\`bash
# Add usage examples here
\`\`\`

## Development
\`\`\`bash
# Add development setup instructions here
\`\`\`

## License
${LICENSE_NOTICE}
EOF
)

GITIGNORE_TEMPLATE=$(cat << 'EOF'
# General
.DS_Store
Thumbs.db
*.log
*.tmp
*.temp
.cache/
.idea/
.vscode/
*.swp
*.swo

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/

# Build outputs
dist/
build/
*.egg-info/

# Environment files
.env
.env.local
.env.production
EOF
)

MIT_LICENSE=$(cat << EOF
MIT License

Copyright (c) $(date +%Y) ${GIT_USER}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
)

###############################################################################
# LANGUAGE-SPECIFIC TEMPLATES
###############################################################################

PYTHON_FILES=(
    "requirements.txt:# Project dependencies"
    "setup.py:# Python setup file"
    "src/__init__.py:# Package initialization"
    "tests/__init__.py:# Tests package"
)

NODEJS_FILES=(
    "package.json:{\n  \"name\": \"${PROJECT_NAME}\",\n  \"version\": \"1.0.0\",\n  \"description\": \"${PROJECT_DESCRIPTION}\",\n  \"main\": \"index.js\",\n  \"scripts\": {\n    \"test\": \"echo \\\"Error: no test specified\\\" && exit 1\"\n  },\n  \"keywords\": [],\n  \"author\": \"${GIT_USER}\",\n  \"license\": \"${LICENSE}\"\n}"
)

BASH_FILES=(
    "src/main.sh:#!/bin/bash\n# Main script for ${PROJECT_NAME}"
)

###############################################################################
# UTILITY FUNCTIONS
###############################################################################

usage() {
    cat <<EOF
Advanced Project Initialization Script
Usage: $0 [OPTIONS] PROJECT_NAME

Options:
  -d, --description DESCRIPTION   Set project description
  -l, --license LICENSE           Set license (MIT, GPL-3.0, Apache-2.0, BSD-3-Clause, None)
  -t, --type TYPE                 Set project type (python, node, bash, web)
  -u, --user USERNAME             Set Git username
  -e, --email EMAIL               Set Git email
  -g, --github                    Create GitHub repository (requires gh CLI)
  -n, --no-commit                 Skip initial commit
  -h, --help                      Show this help message

Examples:
  $0 my-project
  $0 -d "A wonderful project" -t python my-project
  $0 -l MIT -g my-project
Environment variables:
  PROJECTS_DIR, DEFAULT_GIT_USER, DEFAULT_GIT_EMAIL, DEFAULT_LICENSE
EOF
}

detect_project_type() {
    local project_name=$1
    local forced_type=$2
    if [ -n "$forced_type" ]; then
        echo "$forced_type"
        return
    fi
    case "$project_name" in
        *python*|*py*) echo "python" ;;
        *node*|*js*|*npm*) echo "node" ;;
        *bash*|*shell*|*sh*) echo "bash" ;;
        *web*|*html*|*css*) echo "web" ;;
        *) echo "general" ;;
    esac
}

create_language_files() {
    local project_type=$1
    local project_dir=$2
    case "$project_type" in
        python)
            echo "Creating Python project structure..."
            for file_info in "${PYTHON_FILES[@]}"; do
                IFS=':' read -r file_path content <<< "$file_info"
                mkdir -p "$project_dir/$(dirname "$file_path")"
                echo -e "$content" > "$project_dir/$file_path"
            done
            ;;
        node)
            echo "Creating Node.js project structure..."
            for file_info in "${NODEJS_FILES[@]}"; do
                IFS=':' read -r file_path content <<< "$file_info"
                mkdir -p "$project_dir/$(dirname "$file_path")"
                eval "echo -e \"$content\"" > "$project_dir/$file_path"
            done
            ;;
        bash)
            echo "Creating Bash project structure..."
            for file_info in "${BASH_FILES[@]}"; do
                IFS=':' read -r file_path content <<< "$file_info"
                mkdir -p "$project_dir/$(dirname "$file_path")"
                echo -e "$content" > "$project_dir/$file_path"
                chmod +x "$project_dir/$file_path"
            done
            ;;
        web)
            echo "Creating web project structure..."
            cat > "$project_dir/index.html" << EOF
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${PROJECT_NAME}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Welcome to ${PROJECT_NAME}</h1>
    <script src="script.js"></script>
</body>
</html>
EOF
            cat > "$project_dir/style.css" << EOF
/* Styles for ${PROJECT_NAME} */
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    line-height: 1.6;
}
EOF
            cat > "$project_dir/script.js" << EOF
// JavaScript for ${PROJECT_NAME}
console.log('${PROJECT_NAME} loaded');
EOF
            ;;
    esac
}

create_github_repo() {
    local project_dir=$1
    local project_name=$2
    local description=$3
    if ! command -v gh &> /dev/null; then
        echo "Warning: GitHub CLI (gh) not installed. Skipping GitHub repo creation."
        echo "Install gh: https://cli.github.com/"
        return 1
    fi
    cd "$project_dir" || return 1
    echo "Creating GitHub repository..."
    if gh repo create "$project_name" --description "$description" --private --push > /dev/null 2>&1; then
        echo "✅ GitHub repository created successfully"
        return 0
    else
        echo "❌ Failed to create GitHub repository"
        return 1
    fi
}

###############################################################################
# ARG PARSING AND MAIN FLOW
###############################################################################

PROJECT_DESCRIPTION="A new project"
LICENSE="$DEFAULT_LICENSE"
PROJECT_TYPE=""
GIT_USER="$DEFAULT_GIT_USER"
GIT_EMAIL="$DEFAULT_GIT_EMAIL"
CREATE_GH_REPO=$CREATE_GITHUB_REPO
DO_INIT_COMMIT=$DEFAULT_INIT_COMMIT

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--description) PROJECT_DESCRIPTION="$2"; shift 2 ;;
        -l|--license) LICENSE="$2"; shift 2 ;;
        -t|--type) PROJECT_TYPE="$2"; shift 2 ;;
        -u|--user) GIT_USER="$2"; shift 2 ;;
        -e|--email) GIT_EMAIL="$2"; shift 2 ;;
        -g|--github) CREATE_GH_REPO=1; shift ;;
        -n|--no-commit) DO_INIT_COMMIT=0; shift ;;
        -h|--help) usage; exit 0 ;;
        -* ) echo "Unknown option: $1"; usage; exit 1 ;;
        *) PROJECT_NAME="$1"; shift ;;
    esac
done

if [ -z "$PROJECT_NAME" ]; then
    echo "Error: Project name is required"
    usage
    exit 1
fi

if [[ ! "$PROJECT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: Project name can only contain letters, numbers, hyphens, and underscores"
    exit 1
fi

if [ -z "$PROJECT_TYPE" ]; then
    PROJECT_TYPE=$(detect_project_type "$PROJECT_NAME")
fi

# shellcheck disable=SC2034  # LICENSE_NOTICE is read by README_TEMPLATE through eval
case "$LICENSE" in
    MIT) LICENSE_NOTICE="This project is licensed under the MIT License - see the LICENSE file for details." ;;
    GPL-3.0) LICENSE_NOTICE="This project is licensed under the GPL-3.0 License - see the LICENSE file for details." ;;
    Apache-2.0) LICENSE_NOTICE="This project is licensed under the Apache-2.0 License - see the LICENSE file for details." ;;
    BSD-3-Clause) LICENSE_NOTICE="This project is licensed under the BSD-3-Clause License - see the LICENSE file for details." ;;
    None) LICENSE_NOTICE="All rights reserved." ;;
    *) echo "Warning: Unknown license '$LICENSE'. Using MIT."; LICENSE="MIT"; LICENSE_NOTICE="This project is licensed under the MIT License - see the LICENSE file for details." ;;
esac

###############################################################################
# PROJECT CREATION
###############################################################################

echo "🚀 Creating new project: $PROJECT_NAME"
echo "📍 Location: $PROJECTS_DIR/$PROJECT_NAME"
echo "📝 Description: $PROJECT_DESCRIPTION"
echo "🔧 Type: $PROJECT_TYPE"
echo "📄 License: $LICENSE"
echo "👤 Git User: $GIT_USER <$GIT_EMAIL>"
echo ""

mkdir -p "$PROJECTS_DIR"

if [ -d "$PROJECTS_DIR/$PROJECT_NAME" ]; then
    echo "Error: Project directory already exists: $PROJECTS_DIR/$PROJECT_NAME"
    exit 1
fi

echo "Step 1/6: Creating project structure..."
mkdir -p "$PROJECTS_DIR/$PROJECT_NAME"
cd "$PROJECTS_DIR/$PROJECT_NAME" || exit 1

echo "Step 2/6: Initializing Git repository..."
git init
git config user.name "$GIT_USER"
git config user.email "$GIT_EMAIL"

echo "Step 3/6: Creating project files..."
eval "echo \"$README_TEMPLATE\"" > README.md
echo "$GITIGNORE_TEMPLATE" > .gitignore

if [ "$LICENSE" != "None" ]; then
    case "$LICENSE" in
        MIT) echo "$MIT_LICENSE" > LICENSE ;;
        *) echo "# $LICENSE License" > LICENSE; echo "Please add $LICENSE license text here" >> LICENSE ;;
    esac
fi

create_language_files "$PROJECT_TYPE" "$PWD"

echo "Step 4/6: Generating project structure..."
PROJECT_TREE=$(find . -type f | sed 's|^\./||' | sort | head -10)

# Inject tree into README
temp_file=$(mktemp)
awk -v tree="$PROJECT_TREE" '
    /^## Project Structure/ {print; getline; print; print "```"; print tree; print "```"; while(getline && !/^## /) {}; if($0 ~ /^## /) print}
    !/^## Project Structure/ {print}
' README.md > "$temp_file" && mv "$temp_file" README.md

if [ "$DO_INIT_COMMIT" -eq 1 ]; then
    echo "Step 5/6: Making initial commit..."
    git add .
    git commit -m "Initial commit: Project setup

- Initialize project structure
- Add README, license, and gitignore
- Set up $PROJECT_TYPE template
- Project: $PROJECT_DESCRIPTION"
fi

if [ "$CREATE_GH_REPO" -eq 1 ]; then
    echo "Step 6/6: Setting up GitHub repository..."
    create_github_repo "$PWD" "$PROJECT_NAME" "$PROJECT_DESCRIPTION"
else
    echo "Step 6/6: Skipping GitHub repository creation (use -g to enable)"
fi

echo ""
echo "✅ Project created successfully!"
echo ""
echo "📁 Project Location: $PWD"
echo "🔧 Project Type: $PROJECT_TYPE"
echo "📄 License: $LICENSE"
echo "👤 Git configured: $GIT_USER <$GIT_EMAIL>"
echo ""

if [ "$DO_INIT_COMMIT" -eq 1 ]; then
    echo "📦 Initial commit: $(git log --oneline -1)"
fi

if [ "$CREATE_GH_REPO" -eq 0 ]; then
    echo "🌐 To create GitHub repository later:"
    echo "   cd $PWD"
    echo "   gh repo create --public --push"
fi

echo ""
echo "🚀 Next steps:"
echo "   cd $PWD"
echo "   Start coding!"
echo ""
