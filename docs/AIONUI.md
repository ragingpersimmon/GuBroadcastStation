# Running Gu with AionUi on kwon9000

AionUi runs the droplet chores and the routine checks, using your local 27B (Ollama), so Claude is only needed
for real development. Everything goes through `scripts/gu.ps1` (SSH to the droplet). AionUi never needs to
click anything.

## 1. One-time setup (about 5 minutes)

1. **Model.** AionUi → Settings → Model → add platform **Custom**:
   - API URL: `http://100.111.143.71:11434/v1`. Ollama listens on your Tailscale address only, so `localhost` won't work.
   - Model: your 27B tag (`ollama list` shows it). API key: any text, e.g. `ollama`.
2. **Workspace.** In PowerShell:
   ```
   cd $env:USERPROFILE; git clone https://github.com/ragingpersimmon/GuBroadcastStation.git
   ```
   In AionUi, open `C:\Users\<you>\GuBroadcastStation` as the workspace.
3. **SSH.** In PowerShell inside that folder, run `.\scripts\gu.ps1 ssh-test`. It must print `ok:`.
   If it says *Permission denied (publickey)*:
   - `type $env:USERPROFILE\.ssh\id_ed25519.pub` must match a line in the droplet's `/root/.ssh/authorized_keys`. Add it from the DigitalOcean web console.
   - Or set `$env:GU_KEY` to the private key file that matches the public key you added.
4. **Assistant instructions.** Create an AionUi assistant "Gu ops" and paste:

> You operate Gu Broadcasting Station from the GuBroadcastStation workspace on Windows. Run tasks only through
> `.\scripts\gu.ps1 <task>` in PowerShell. Read-only tasks you may run any time: ssh-test, doctor, newsroom,
> inquiries, logs, llm-check. Ask Ric before `deploy`, and never run `harden` or reboot the droplet yourself.
> Never edit the droplet's .env, never print secrets, never touch vendor/5protocol or any other app on the
> droplet (it also hosts Vantage Supplements). Rules for the newsroom are in AGENTS.md: sources stay
> confidential and nothing is published unless the verification engine passes it. Do not change those rules.
> When you report, be terse: what is wrong, what you'd do, and the exact command.

## 2. Scheduled tasks in AionUi

| When | Prompt |
|---|---|
| Daily 07:10 | "Run `.\scripts\gu.ps1 doctor` and `.\scripts\gu.ps1 newsroom`. Report only lines marked [FIX] or [WARN], silent feeds, and the top held-back reasons. If all is OK, say 'Gu OK'." |
| Weekdays 09:05 | "Run `.\scripts\gu.ps1 inquiries`. For each open inquiry older than 24 h, tell me the reference, company and what they want." |
| Hourly | "Run `.\scripts\gu.ps1 llm-check`. Only tell me if it fails (then nothing new publishes on gubs.ca)." |

## 3. Things to ask Gu ops

- "Deploy the latest main to gubs.ca." It runs `gu.ps1 deploy`, then `gu.ps1 doctor`.
- "Why were stories held back today?" It runs `gu.ps1 newsroom` and reads the reasons.
- "Mark GU-261110-7F3K booked." It runs `gu.ps1 reply GU-261110-7F3K -Status booked`.
- "Is the site healthy?" It runs `gu.ps1 doctor`.

## Limits

- The 27B is good at running these scripts and summarising their output. Code changes to the newsroom (the
  verification engine, site builder, security config) still go through a reviewed pull request with tests.
- Keep kwon9000 awake and Ollama running: it is also the newsroom's only writer and translator.
