# Lenovo home server: agent runbook

You are Claude Code on Carter's Lenovo, inside WSL Ubuntu. Carter has finished the
bootstrap in [`README.md`](README.md): base packages, systemd, Tailscale (`lenovo`),
linger, Windows settings, Claude account A in `~/.claude-a`, and this repo at
`~/repos/body-of-christ`. Your job is to turn this into the always-on home server
described there.

How to run this:

- Do the steps in order. Each ends on a **Done when** line: check it with a command and
  show Carter the output before moving on.
- **Carter does** marks a step only he can do (a sign-in, a browser link, an email, a
  `sudo` password). Give him the exact command to paste into a *separate* Ubuntu
  terminal, then wait for him to say it's done and verify it yourself.
- Your Bash tool cannot answer a `sudo` password prompt. Anything needing `sudo` is a
  Carter step.
- If a step fails, stop and report the command and its output. Change nothing outside
  this runbook's scope to work around it.
- Commit and push nothing. This runbook changes the machine, not the repo.

`$REPO` below is `$HOME/repos/body-of-christ`.

Your Bash tool doesn't load `~/.bashrc`, so after step 2 installs nvm, `node`, `npm`
and `codex` are not on its PATH. Start every command that needs them with
`. ~/.nvm/nvm.sh &&`.

## 1. Check the bootstrap

Run and report: `grep -i microsoft /proc/version`, `echo $WSL_DISTRO_NAME`,
`systemctl is-system-running`, `loginctl show-user "$USER" -p Linger`,
`tailscale status`, `gh auth status`, `free -g`, `df -h ~`.

**Done when:** WSL is confirmed, systemd is `running` or `degraded`, `Linger=yes`, and
Tailscale shows this machine as `lenovo` and online. Tell Carter the RAM. With 16 GB or
less, say that two or three sessions running builds at once is the practical limit.

## 2. Node and Codex

Install nvm from its GitHub README (the current `install.sh` one-liner), then
`nvm install --lts` and `nvm alias default 'lts/*'`. Install Codex with
`npm i -g @openai/codex@latest`.

**Carter does:** `codex login --device-auth`, signing in with his ChatGPT account.

**Done when:** `node --version` is 20 or later, `codex login status` shows him signed
in, and `codex debug models` lists a `*-sol` model, which sol-loop needs.

## 3. Git identity

Set `user.name` and `user.email` globally from the repo's own history
(`git -C $REPO log -1 --format='%an%n%ae' --author=Carter`). Run `gh auth setup-git`.

**Done when:** `git config --global user.email` matches Carter's commits and
`git -C $REPO fetch` succeeds.

## 4. The two Claude accounts

Install the helpers: `bash $REPO/scripts/home-server/install.sh`. Read the script first.
It replaces `~/.claude-a/settings.json`, which this session started with, by a link to
the shared copy; that's expected, and the session keeps running.
It copies the scripts to `~/.local/share/home-server`, adds a `source` line to
`~/.bashrc`, creates `~/.claude-shared` with the machine-level `CLAUDE.md` and a
`settings.json`, links both into `~/.claude-a` and `~/.claude-b`, and installs the
systemd user unit `home-agent@.service`. It does not enable any service yet.

**Carter does,** in a new Ubuntu terminal so `.bashrc` is reloaded:

```bash
cd ~/repos/body-of-christ
claude-b        # sign in with Claude account B, accept the folder trust prompt, /exit
claude-a        # already signed in; accept the folder trust prompt, /exit
```

**Done when:** `ls -l ~/.claude-a/CLAUDE.md ~/.claude-b/CLAUDE.md` show both linking to
`~/.claude-shared/CLAUDE.md`, and Carter confirms both sign-ins. Have him run
`claude-a` then `/status` (and the same for `claude-b`) and read you the account lines:
they must be two different accounts.

## 5. Env files and corpus data from the Mac

The `.env` files are gitignored, so they come from the Mac. Ask Carter to open Claude
Code on the Mac and say: **"Follow docs/setup/home-server/mac.md."** Its step that
copies files needs this machine reachable over Tailscale, which it already is.

**Done when:** `$REPO/apps/web/.env.local`, `$REPO/services/api/.env` and
`$REPO/datapipeline/.env` exist with mode 600 (`stat -c '%a %n'`). Do not print their
contents. If Carter chose to copy the corpus data, `$REPO/datapipeline/sources` exists too.

## 6. Main checkout dependencies

In `$REPO`: `npm ci` in `apps/web`; a venv at `services/api/.venv` with
`pip install --require-hashes -r requirements-dev.lock && pip install --no-deps -e .`;
a venv at `datapipeline/.venv` with `pip install --require-hashes -r requirements.lock`.

Install headless Chromium so agents can check pages with Playwright. Playwright isn't a
dependency of `apps/web`, so pick one version (the latest, from `npm view playwright version`)
and use it in all three places:

- `npm i -g playwright@<v> && playwright install chromium`
- **Carter does** the system libraries: `sudo env "PATH=$PATH" playwright install-deps chromium`
- check: in a scratch folder, `npm i playwright@<v>` and run a script that launches
  Chromium, loads `https://example.com` and prints the title.

**Done when:** `npm test` passes in `apps/web`,
`services/api/.venv/bin/python -c "import app.main"` exits 0 from `services/api`, and
the Playwright check prints `Example Domain`. Report
any test failure as-is; it may be a real failure on master, not a setup problem.

## 7. Worktree setup works

Prove the worktree path end to end. The check worktree starts from the checkout's
`HEAD`, which has these scripts even if they aren't merged to master yet.

```bash
git -C $REPO worktree add -b tmp/setup-check ../wt-setup-check HEAD
cd ~/repos/wt-setup-check && ~/.local/share/home-server/worktree-setup.sh
```

**Done when:** the worktree has the three env files as symlinks into `$REPO`,
`npm test` passes in its `apps/web`, and its API venv imports `app.main`. Then remove it:
`git -C $REPO worktree remove ../wt-setup-check && git -C $REPO branch -D tmp/setup-check`.

## 8. Remote Control services

Check the exact commands before enabling anything:

- `claude remote-control --help`: confirm `--spawn worktree` exists.
- `codex remote-control --help`: confirm `--no-daemon` exists. The service runs
  `codex remote-control --no-daemon` (foreground), not `start`, which forks a daemon and
  returns. If the flag is gone, report it and skip the Codex service.

**Carter does** the first run of each in a separate terminal, so any one-time prompt
(enabling Remote Control, naming the environment) is answered by a person:

```bash
cd ~/repos/body-of-christ
claude-a remote-control --spawn worktree    # answer prompts, confirm it shows in the Claude app, Ctrl-C
claude-b remote-control --spawn worktree    # same, with the app switched to account B
codex remote-control start                  # pairing needs the daemon: `pair` talks to its control
codex remote-control pair                   # socket, which --no-daemon doesn't create. In the ChatGPT
                                            # app's Codex machine list: add → "Pair manually", enter the code
codex remote-control stop                   # the service runs its own --no-daemon copy
```

The Lenovo shows in the ChatGPT app under its Windows name (`LAPTOP-EBQLQ579`), not
`lenovo`.

Then enable the services: `home-agents enable`.

**Done when:** `home-agents status` shows `home-agent@claude-a`, `home-agent@claude-b`
and `home-agent@codex` active, and Carter confirms on his phone that each Claude account
lists the Lenovo and the ChatGPT app lists it under Remote. Show him
`tmux -L claude-a attach` (detach with `Ctrl-b d`) so he knows where to look when one
misbehaves.

## 9. Reboot test

**Carter does:** restart Windows and sign in (or let automatic sign-in do it), then wait
two minutes without opening Ubuntu.

**Done when:** from his phone or the Mac, the Claude app shows the Lenovo for both
accounts again and `ssh lenovo '~/.local/bin/home-agents status'` shows all three active. If they did
not come back, check the Windows task first (`Get-ScheduledTask -TaskName 'Keep WSL
running'` in PowerShell), then `journalctl --user -u 'home-agent@*'`. If `home-agents
status` says there is no systemd user bus, WSLg is still on: check `.wslconfig` (README,
step f), and for now `sudo umount /run/user/$(id -u)`.

## 10. Report

Tell Carter what is installed, the RAM limit from step 1, anything you changed from this
runbook (such as the Codex command), and which steps he still owes: the ROG
([`rog.md`](rog.md)) and the iPhone ([`iphone.md`](iphone.md)).
