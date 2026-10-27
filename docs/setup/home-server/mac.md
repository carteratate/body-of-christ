# Mac: agent runbook

You are Claude Code on Carter's MacBook Air. The Lenovo home server (see
[`README.md`](README.md)) is partway through its own setup and is waiting on you for
step 3. Your job: connect this Mac to the Lenovo, send it the files git doesn't carry,
and set up the ways Carter works on the Lenovo from here.

Do the steps in order. Each ends on a **Done when** line: verify it and show Carter.
**Carter does** marks a step only he can do; give him the exact action and wait.
Commit and push nothing.

## 1. Tailscale

**Carter does:** install Tailscale from tailscale.com/download (or the Mac App Store),
open it, and sign in with the same Tailscale account as the Lenovo.

**Done when:** `/Applications/Tailscale.app/Contents/MacOS/Tailscale status` lists
`lenovo` as online, and `.../Tailscale ping lenovo` gets a reply.

## 2. SSH to the Lenovo

Ask Carter for his Linux user name on the Lenovo (`whoami` in Ubuntu there). Add this
block to `~/.ssh/config` if no `Host lenovo` exists, and show him the result:

```
Host lenovo
  HostName lenovo
  User <linux user>
```

**Done when:** `ssh lenovo 'uname -a && ls ~/repos'` prints a Linux kernel with
`microsoft` in it and `body-of-christ`. Tailscale SSH may first print a sign-in link
instead; Carter opens it, then you retry.

## 3. Send the gitignored files

Confirm with Carter, then copy the three env files from this checkout
(`/Users/cartertate/repos/body-of-christ`) into the same paths under
`~/repos/body-of-christ` on the Lenovo with `scp -p`:
`apps/web/.env.local`, `services/api/.env`, `datapipeline/.env`. Then
`ssh lenovo 'chmod 600 ...'` on all three. Never print their contents.

Ask Carter whether he'll run datapipeline work on the Lenovo. If yes, also copy
`datapipeline/sources/` and `datapipeline/releases/snapshots/` (about 290 MB) with
`rsync -a` (`scp -rp` if rsync is missing there).

**Done when:** `ssh lenovo "stat -c '%a %n' ~/repos/body-of-christ/{apps/web/.env.local,services/api/.env,datapipeline/.env}"`
shows `600` for all three, and the byte counts match `wc -c` on this Mac.
Tell Carter the Lenovo session can continue from its step 5.

## 4. Editor over Remote-SSH

Find which editor CLIs exist (`command -v cursor code`). For VS Code, install
`ms-vscode-remote.remote-ssh` with `code --install-extension`. Cursor ships its own
Remote-SSH; check `cursor --list-extensions` and install it only if it is missing.

**Carter does:** in the editor, Command Palette → **Remote-SSH: Connect to Host** →
`lenovo`, then open `~/repos/body-of-christ`. In its terminal: `claude-a`.

**Done when:** Carter confirms the editor shows the Lenovo's files and `claude-a` starts
signed in as account A. Point out tmux: `tmux new -A -s work` keeps terminal sessions
alive when he closes the laptop, and he reattaches with the same command.

## 5. Both accounts in the browser

**Carter does:** sign into claude.ai with account A in one browser (or Chrome profile)
and account B in another. Each stays signed in, so `claude.ai/code` in each shows that
account's Lenovo sessions side by side, with no switching.

**Done when:** each browser lists the Lenovo under its account.

## 6. Optional: the Claude desktop app over SSH

The Claude desktop app can run Code sessions on an SSH host. **Carter does:** add
`lenovo` as an SSH connection and start a session there. Check `/status` in it to see
which account it uses, since that isn't settled yet. Report what he finds; nothing
else in this setup depends on it.

## 7. Report

Tell Carter what is set up on this Mac and what is left: the Lenovo's remaining steps,
then [`rog.md`](rog.md) and [`iphone.md`](iphone.md).
