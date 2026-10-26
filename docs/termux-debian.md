# Termux + PRoot Debian workstation setup

Updated 2026-10-26: placeholders replace personal values, and checks run through `jadis`. The original is
in git history; see [migration.md](migration.md).

Throughout, `<user>`, `<name>` and `<email>` are yours to fill in.

## 0. Termux (native)

```sh
termux-setup-storage                 # grant storage; needs you on the device
pkg update && pkg upgrade
pkg install git openssh gnupg proot-distro curl tar unzip clang make python nodejs
pkg install ripgrep fzf jq           # optional
```

Then install jadis (README) and check: `jadis doctor --profile termux`.

Git identity is yours to set; jadis never sets it:

```sh
git config --global user.name "<name>"
git config --global user.email "<email>"
jadis repair git-default-branch      # sets init.defaultBranch main (shows the plan, asks first)
```

## 1. Debian 13 via proot-distro

```sh
proot-distro install debian
proot-distro login debian            # you start as (fake) root
apt-get update && apt-get upgrade
apt-get install locales sudo tzdata
dpkg-reconfigure locales             # choose a UTF-8 locale
dpkg-reconfigure tzdata
adduser <user> && usermod -aG sudo <user>
exit
proot-distro login debian --user <user>
```

Inside Debian, `jadis env` should report `proot-debian`, and `jadis debian` checks apt, sudo, locale and
PRoot specifics.

## 2. Developer stack inside Debian

```sh
jadis bootstrap outer-void --plan    # shows exactly which apt packages are missing
jadis bootstrap outer-void           # installs them after you confirm
sudo apt-get install build-essential pkg-config libssl-dev neovim    # extras jadis does not manage
```

Java and Android: `jadis bootstrap java --plan`, then `jadis android` for the SDK.

## 3. Shell (Zsh)

```sh
sudo apt-get install zsh && chsh -s /usr/bin/zsh <user>
```

Oh My Zsh, Powerlevel10k, zplug and zinit are third-party projects. Their one-line installers download and
run code. Read an installer before running it, or clone the project and follow its README:

```sh
git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git ~/.oh-my-zsh      # then read its install docs
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k
```

Snapshot your shell config before large changes (`jadis backup shell`), and check for shadowed commands
afterwards (`jadis shell`).

## 4. GitHub SSH (Termux and Debian are separate homes)

```sh
ssh-keygen -t ed25519 -C "<email>"   # you decide; jadis never generates or uploads keys
cat ~/.ssh/id_ed25519.pub            # add this public key on GitHub (Settings → SSH keys)
jadis ssh                            # checks ~/.ssh and key permissions and the agent
jadis repair ssh-permissions         # fixes modes if needed (plan shown first)
ssh -T git@github.com                # explicit network check, run by you
```

## 5. Cloning and working

```sh
git clone git@github.com:Outer-Void/<repo>.git && cd <repo>
jadis doctor --profile outer-void
```

## 6. Quality of life

```sh
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519     # per session
jadis python venv                                      # project-local venv (docs/python.md)
```

Set `EDITOR=nvim` in your own startup file. jadis only ever edits marked blocks.

## 7. Moving a personal setup bundle in

```sh
cp /sdcard/<your-folder>/<bundle>.tar.gz ~/ && tar -xzf ~/<bundle>.tar.gz -C ~/setup
jadis backup shell                   # snapshot before overwriting dotfiles
rsync -av ~/setup/dotfiles/ ~/
```

Keeping dotfiles in a Git repository is simpler.

## 8. Common problems

| Symptom | Check / fix |
|---|---|
| `UNPROTECTED PRIVATE KEY FILE!` | `jadis ssh`, then `jadis repair ssh-permissions` |
| `Permission denied (publickey)` | Is the public key on GitHub? Does `~/.ssh/config` use the right `IdentityFile`? |
| Tools behave oddly in Debian | `jadis shell`: Termux binaries leaking onto the guest PATH, or shadowed commands |
| Garbled characters | `jadis debian` locale check, then `dpkg-reconfigure locales` |
| Out of space | `jadis doctor` reports free space; keep large repos and venvs in one environment |
| neofetch battery errors | Comment out the battery line in `~/.config/neofetch/config.conf` |

## 9. Ready?

```sh
jadis doctor --profile outer-void
jadis report --out .jadis/environment.json      # keep it; diff it later with `jadis env diff`
```
