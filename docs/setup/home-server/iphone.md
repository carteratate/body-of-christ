# iPhone: checklist

No agent here; these are yours. About 10 minutes.

1. **Tailscale.** Install it from the App Store and sign in with the same Tailscale
   account. Leave it on: it only routes traffic for your own devices, so it costs
   little battery.
2. **Claude app.** Sign into account A and account B (you already switch between them).
   Under Code, each account lists the Lenovo once its Remote Control service is up.
   Start a session there and it works in its own worktree on the Lenovo.
3. **ChatGPT app.** In Codex's machine list, add → "Pair manually" and enter the code
   from `codex remote-control pair` on the Lenovo (its runbook, step 8, walks you
   through it). The Lenovo is listed as `LAPTOP-EBQLQ579`.
4. **Termius** (or Blink) for when something is stuck. Skip the Termius account it asks
   for: that only syncs hosts between devices and has nothing to do with Tailscale. Add a
   host: address `lenovo` (or its Tailscale IP), port 22, user `carter`, no password or
   key. Tailscale SSH handles sign-in, and may show a link to approve now and then. The
   commands you need:
   - `home-agents status`: are the three services running?
   - `home-agents restart`: restart them.
   - `tmux -L claude-a attach`: see one service's output (`Ctrl-b d` to leave).
5. **Safari.** When an agent says a dev server is up, it gives you
   `http://lenovo:<port>`. Signing in to TheoCorpus there fails until that address is
   on the Supabase redirect list, which is a production auth setting and your call.
   Signed-out pages work.

**Done when:** from cellular with Wi-Fi off, the Claude app shows the Lenovo for both
accounts, the ChatGPT app shows it under Remote, and `home-agents status` works in
Termius.
