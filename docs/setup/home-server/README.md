# Home server setup

The Lenovo stays at home, always on, and runs every agent. The Mac, the ROG and the
iPhone are screens for it: they reach it through the Claude and ChatGPT apps (Remote
Control) and through Tailscale (SSH, dev servers in the browser).

```
iPhone ─┐                       Lenovo (Windows → WSL Ubuntu, hostname "lenovo")
Mac ────┼── Tailscale ─────────►  claude-a remote-control   (Claude account A)
ROG ────┘   Claude / ChatGPT ──►  claude-b remote-control   (Claude account B)
                                  codex remote-control      (ChatGPT account)
                                  ~/repos/body-of-christ + one worktree per session
```

## Your order of operations

You do a short bootstrap by hand on the Lenovo. After that, Claude Code on each machine
follows that machine's guide and stops whenever it needs you (a sign-in, an email link,
a `sudo` password, a Windows setting). Have the Lenovo and the Mac side by side: they
hand off to each other once.

1. **Lenovo, by hand:** the bootstrap in section 1 below, steps a–f. It ends with
   Claude Code installed and signed in as account A, and this repo cloned.
2. **Lenovo, Claude:** step g starts Claude in the repo. Tell it:
   *"Follow docs/setup/home-server/lenovo.md."* It runs steps 1–4, then at step 5 asks
   you to switch to the Mac.
3. **Mac, Claude:** open Claude Code in `~/repos/body-of-christ` (`git pull` first so
   the guide is there) and tell it: *"Follow docs/setup/home-server/mac.md."* Its step 3
   copies the `.env` files to the Lenovo; it then tells you the Lenovo can continue.
   Let it finish steps 4–7 whenever suits you.
4. **Lenovo, Claude:** back in the same session, say *"The Mac sent the files; continue
   from step 5."* It finishes steps 5–10, including turning on the services and a
   reboot test where you restart Windows.
5. **ROG, Claude:** open Claude Code in the repo there (`git pull` first) and tell it:
   *"Follow docs/setup/home-server/rog.md."*
6. **iPhone, you:** [`iphone.md`](iphone.md). Do it last, since it checks that
   everything above works from cellular.

If the Lenovo session ends partway (a WSL restart, a closed terminal), start Claude
again in the repo and say *"Continue docs/setup/home-server/lenovo.md from step N"*;
each step's **Done when** check tells it what is already finished.

The scripts the guides install are in [`scripts/home-server/`](../../../scripts/home-server/).

## 1. Bootstrap the Lenovo (by hand, about 20 minutes)

These steps need `sudo` or a WSL restart, which an agent can't do from inside its own
session, so they come first.

**a. Check WSL.** In PowerShell:

```powershell
wsl -l -v
```

You want an Ubuntu distro on version 2. If there is none, run `wsl --install -d Ubuntu`,
restart, and create your Linux user when it asks.

**b. Install the base packages and turn on systemd.** Open the Ubuntu terminal and paste:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git curl tmux jq unzip ca-certificates python3-venv python3-pip
# GitHub CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install -y gh
# systemd, so services start with WSL
cat /etc/wsl.conf 2>/dev/null   # keep anything already here
grep -q '^systemd=true' /etc/wsl.conf 2>/dev/null || printf '\n[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf
```

If the file already had a `[boot]` section, merge the two by hand (`sudo nano /etc/wsl.conf`).
Then in PowerShell run `wsl --shutdown`, and reopen Ubuntu. Check that
`systemctl is-system-running` prints `running` or `degraded` (either is fine).

**c. Tailscale, and services that run without you logged in.** In Ubuntu:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh --hostname lenovo --accept-dns=false
sudo loginctl enable-linger "$USER"
```

`tailscale up` prints a link. Open it in Windows and sign in with the Tailscale account
you'll use on every device. Then, in the Tailscale admin console (login.tailscale.com):

- **Machines → lenovo → ⋯ → Disable key expiry.** Otherwise it drops off the network
  in about six months and needs a sign-in at the machine.
- **Access controls → SSH:** if the rule for your own devices says `"action": "check"`,
  change it to `"accept"`. `check` asks you to re-approve in a browser every so often,
  and editors connecting over Remote-SSH can hang on that prompt.

`--accept-dns=false` leaves WSL's own DNS setup alone; Tailscale names still resolve
from your other devices.

**d. Claude Code, signed in as account A.** Install the terminal version inside Ubuntu,
not the Windows desktop app. The services, worktrees and Remote Control all run in WSL,
and a Windows app would work on the Windows side instead. You can still add the desktop
app later for your own use. In Ubuntu:

```bash
curl -fsSL https://claude.ai/install.sh | bash
mkdir -p ~/repos
CLAUDE_CONFIG_DIR=~/.claude-a ~/.local/bin/claude
```

Sign in with Claude account **A** (open the link in Windows, click the email), then
`/exit`.

**e. The repo.** In Ubuntu:

```bash
gh auth login        # GitHub.com → HTTPS → log in with a browser
gh repo clone carteratate/body-of-christ ~/repos/body-of-christ
```

If this guide isn't merged to master yet, switch to the branch it's on:
`git -C ~/repos/body-of-christ checkout docs/home-server-setup`.

**f. Windows settings.** Copy the setup script to Windows, then run it from PowerShell
**as administrator** (an elevated shell can't always read WSL paths). In Ubuntu:

```bash
cd /mnt/c && cp ~/repos/body-of-christ/scripts/home-server/windows-setup.ps1 "$(wslpath "$(cmd.exe /c 'echo %USERPROFILE%' | tr -d '\r')")/"
```

Then, in the administrator PowerShell, where `<distro>` is the name `wsl -l -v` showed:

```powershell
powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\windows-setup.ps1 -Distro <distro>
```

It stops sleep and hibernation on AC power, makes closing the lid do nothing, and adds a
sign-in task that starts WSL and keeps it running. Then, in Settings:

- **Windows Update → Advanced options → Active hours:** cover the hours you use agents,
  or pause updates a few weeks at a time.
- **Lenovo Vantage → Power → Conservation mode:** on. It caps the battery around 60%,
  which matters for a laptop plugged in all the time.
- **Optional, Accounts → Sign-in options:** automatic sign-in. WSL only starts after
  someone signs in, so without it the Lenovo stays offline after an unattended reboot
  until you get home. The trade-off: anyone holding the laptop gets in.

**g. Hand over.** Start Claude in the repo and give it the guide:

```bash
cd ~/repos/body-of-christ
CLAUDE_CONFIG_DIR=~/.claude-a ~/.local/bin/claude
```

> Follow docs/setup/home-server/lenovo.md.

## Using it day to day

- **Phone:** Claude app (switch accounts to see each one's sessions), ChatGPT app for
  Codex, Safari at `http://lenovo:<port>` for a dev server, Termius when something is stuck.
- **Laptop:** Cursor or VS Code → Remote-SSH → `lenovo`, then `claude-a` / `claude-b` in
  tmux. Or claude.ai/code in two browser profiles, one per account.
- **Something stopped?** `ssh lenovo`, then `home-agents status` and `home-agents restart`.
