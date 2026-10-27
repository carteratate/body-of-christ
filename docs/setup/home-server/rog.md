# ROG G14: agent runbook

You are Claude Code on Carter's ROG G14, running either in Windows or in WSL there
(`uname -s` tells you: `Linux` means WSL). The Lenovo home server
([`README.md`](README.md)) is already running. Your job: connect this laptop to it and
set up the ways Carter works on the Lenovo from here. This laptop runs no agent
services of its own, and sol-loop keeps working here as before.

Do the steps in order. Each ends on a **Done when** line: verify it and show Carter.
**Carter does** marks a step only he can do; give him the exact action and wait.
Commit and push nothing.

## 1. Tailscale

**Carter does:** install Tailscale for Windows from tailscale.com/download and sign in
with the same Tailscale account as the Lenovo. One install covers WSL too: WSL's
traffic goes out through Windows.

**Done when:** `tailscale status` in PowerShell lists `lenovo` as online.

## 2. SSH to the Lenovo

Ask Carter for his Linux user name on the Lenovo. Add a `Host lenovo` block
(`HostName lenovo`, `User <linux user>`) to the Windows SSH config,
`%USERPROFILE%\.ssh\config`, which the editors use. If you are in WSL, add the same
block to `~/.ssh/config` there too.

Test `ssh lenovo uname -a` from PowerShell, and from WSL if you are in it. WSL may not
resolve the short name `lenovo`. If it doesn't, take the full name from
`tailscale status --json` in PowerShell (the `Peer` entry for lenovo, field `DNSName`,
like `lenovo.<tailnet>.ts.net`) and use it as `HostName` in the WSL config.

**Done when:** `ssh lenovo uname -a` prints the Lenovo's Linux kernel from every shell
Carter uses on this laptop. If Tailscale SSH prints a sign-in link, Carter opens it and
you retry.

## 3. Editor over Remote-SSH

Same as [`mac.md`](mac.md) step 4, with the Windows editor: install Remote-SSH if
missing, then **Carter does** Command Palette → **Remote-SSH: Connect to Host** →
`lenovo` → open `~/repos/body-of-christ`, and runs `claude-a` in its terminal.

**Done when:** Carter confirms the editor shows the Lenovo's files and `claude-a` starts
signed in.

## 4. Both accounts in the browser

Same as [`mac.md`](mac.md) step 5: account A in one browser or profile, account B in
another, each showing its Lenovo sessions at `claude.ai/code`.

**Done when:** each browser lists the Lenovo under its account.

## 5. Report

Tell Carter what is set up and that [`iphone.md`](iphone.md) is the last piece.
