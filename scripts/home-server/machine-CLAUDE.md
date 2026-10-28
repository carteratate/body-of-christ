# This machine: the Lenovo home server

Installed by `scripts/home-server/install.sh` from the body-of-christ repo; edit it
there and re-run the script. Both Claude accounts read this file.

You are on Carter's always-on Lenovo, in WSL Ubuntu, Tailscale hostname `lenovo`.
Carter is not at this machine: he reaches it from his phone and laptops, so anything
you want him to look at must be reachable over Tailscale.

- **Fresh worktree:** run `~/.local/share/home-server/worktree-setup.sh` once before
  running the app or tests in it (add `--datapipeline` for datapipeline work). It links
  the gitignored `.env` files and corpus data from the main checkout.
- **Dev servers:** other sessions may be running theirs. Pick a free port (web from
  3000, API from 8000; check with `ss -ltn`), listen on all interfaces, and give Carter
  the URL as `http://lenovo:<port>`:
  `uvicorn app.main:app --host 0.0.0.0 --port <api>` and
  `API_URL=http://localhost:<api> npm run dev -- -H 0.0.0.0 -p <web>`.
  Stop the servers you started when you finish.
- **Checking pages:** use headless Playwright (Chromium is installed). There is no
  desktop to drive.
- **Production data:** the `.env` files point at the live database and services.
  Reading for a test is fine. A migration, a datapipeline `--release`, or any other
  write needs Carter's explicit OK in this session.
- **Keep the subscription login:** never `source` or `export` a `.env` file into the
  shell. Its `ANTHROPIC_API_KEY` would switch Claude Code to billing that key.
- **Remote control services** (`home-agents status`, tmux sockets `claude-a`,
  `claude-b`, `codex`) keep this machine reachable. Leave them running unless Carter asks.
