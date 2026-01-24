# Termux Debian Setup

0) Termux bootstrap (first run)

### Grant storage access so we can reach /storage/emulated/0/...
```
termux-setup-storage
```
### Core updates
```
pkg update -y && pkg upgrade -y
```
### Essentials (git/ssh/gnupg/build tools/proot-distro)
```
pkg install -y git openssh gnupg proot-distro curl wget tar unzip \
  clang make python nodejs neovim htop rsync
```
### (Optional) Nice-to-haves
```
pkg install -y ripgrep fzf jq
```
Set your global Git identity now (used in both Termux and Debian unless you override):
```
git config --global user.name "Justadudeinspace"
git config --global user.email "theoutervoid@outlook.com"
git config --global init.defaultBranch main
git config --global pull.rebase false
```

---

1) Install Debian (proot-distro)
```
proot-distro install debian
proot-distro login debian
```
Inside Debian (you start as root):
```
# Update base
apt-get update && apt-get upgrade -y

# Locale & sudo
apt-get install -y locales sudo tzdata
dpkg-reconfigure locales   # pick en_US.UTF-8
dpkg-reconfigure tzdata    # pick your timezone (America/Chicago)

# Create a non-root user for daily work
adduser Justadudeinspace 
usermod -aG sudo Justadudeinspace 
```
Exit and log back in as your user:
```
exit
```

```
proot-distro login debian --user Justadudeinspace 
```

---

2) Developer stack inside Debian

# Build tools & common dev kits
```
sudo apt-get update
sudo apt-get install -y build-essential git curl wget unzip zip \
  python3 python3-pip python3-venv \
  nodejs npm \
  neovim pkg-config libssl-dev

# (Optional) Java, if needed for gigs
# sudo apt-get install -y openjdk-17-jdk

# Nice-to-haves
sudo apt-get install -y ripgrep fzf jq htop bat
```

---

3) Shell & dotfiles (Zsh, Oh-My-Zsh, p10k, plugins)

If you already have a personal “developer setup pkg” (zsh/oh-my-zsh/p10k/zplug/zinit/neofetch) saved on device storage, you can copy it straight into Debian (Debian sees your phone storage at /sdcard):
```
# From inside Debian as user 'justa'
# Example: copy your prepared bundle from /sdcard to your home
cp -a /sdcard/jadis.junk/my-debian-dev-setup ~/dev-setup

# If your bundle includes install scripts, run them:
cd ~/dev-setup
# e.g., ./install.sh   (adapt to your package)
```
Or do it manually:
```
# Zsh + Oh-My-Zsh
sudo apt-get install -y zsh
chsh -s /usr/bin/zsh justa  # sets default shell (works in proot)
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Powerlevel10k
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
  ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k
# Then set in ~/.zshrc:
# ZSH_THEME="powerlevel10k/powerlevel10k"

# zplug (if you use it)
curl -fsSL https://raw.githubusercontent.com/zplug/installer/master/installer.zsh | zsh

# zinit (if preferred instead of zplug)
# sh -c "$(curl -fsSL https://git.io/zinit-install)"

# neofetch
sudo apt-get install -y neofetch
# If battery errors annoy you in Termux/Debian, you can disable battery in neofetch config later:
# sed -i 's/info "Battery" battery/# info "Battery" battery/' ~/.config/neofetch/config.conf
```
Reload Zsh:
```
exec zsh
```

---

4) GitHub SSH inside Debian




---

5) Cloning & working

Termux (native) clone example:
```
cd ~
git clone git@github.com:Outer-Void/blux-lite.git
```
Debian (sandbox) clone example:
```
cd ~
git clone git@github.com:Outer-Void/blux-ca.git
```
Push test:
```
cd blux-ca
git status
git pull
# make a tiny change, commit, then push
git add -A
git commit -m "Debian sandbox smoke test"
git push
```

---

6) Quality-of-life & speed

SSH agent (Termux & Debian):
```
# Start agent and add key for the session
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```
Add the ssh-agent lines to your ~/.zshrc (both Termux and Debian) if you want it auto-loaded.

Language runtimes:

Python venv for gigs:
```
python3 -m venv .venv && . .venv/bin/activate
pip install --upgrade pip
```
Node:
```
npm -v && node -v
```

Editor:

nvim is installed in both; set $EDITOR=nvim in your ~/.zshrc.



---

7) Moving your personal Debian setup bundle into place

If your “full personal Debian zsh/oh-my-zsh/.zshrc/p10k/neofetch/zplug/zinit/dev setup pkg” is a tar/zip:
```
# Inside Debian
mkdir -p ~/setup
cp /sdcard/jadis.junk/my-debian-setup.tar.gz ~/setup/
cd ~/setup && tar -xzf my-debian-setup.tar.gz

# Example: if it contains dotfiles
rsync -av --progress dotfiles/ ~/

# Re-source shell
exec zsh
```
> Tip: keep your dotfiles repo on GitHub and just git clone it into Debian. That way your sandbox is one command away from “home base”.




---

8) Common gotchas & fixes

“UNPROTECTED PRIVATE KEY FILE!” → chmod 600 ~/.ssh/id_ed25519

GitHub “permission denied (publickey)” → ensure the public key for id_ed25519 is added to GitHub; verify ~/.ssh/config uses the right IdentityFile.

Oh-My-Zsh install in proot → run as your user (justa), not root. If it asks to change shell, you can run chsh -s /usr/bin/zsh justa.

Neofetch battery errors on Android paths → comment out the battery line in ~/.config/neofetch/config.conf.

Time/locale weirdness → run dpkg-reconfigure tzdata and dpkg-reconfigure locales.

Space issues → watch df -h in Termux; keep large repos and venvs inside Debian where possible.



---

9) Quick “ready for gigs” checklist (Debian)

# inside Debian as 'justa'
```
node -v && npm -v
python3 --version && pip3 --version
gcc --version && make --version
git --version && ssh -T git@github.com
zsh --version && neofetch | head -n 5
```

You’ll now have:

Termux native env (handy for quick pulls/edits).

A self-contained Debian sandbox with your preferred shell & dev tooling.

GitHub SSH auth working in both environments using your encrypted key as the source of truth.
