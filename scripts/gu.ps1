<#
  gu.ps1 - run Gu Broadcasting Station droplet tasks from kwon9000 (for Ric or AionUi).

    .\scripts\gu.ps1 ssh-test      check the SSH key works
    .\scripts\gu.ps1 deploy        pull main, install configs, restart, rebuild (deploy/update.sh)
    .\scripts\gu.ps1 doctor        read-only health + security audit (deploy/doctor.sh)
    .\scripts\gu.ps1 newsroom      `gbs doctor`: rewriter, feeds, verification pass/hold
    .\scripts\gu.ps1 inquiries     open work-with-us inquiries
    .\scripts\gu.ps1 reply GU-...  mark an inquiry replied (also: booked | declined | spam via -Status)
    .\scripts\gu.ps1 logs          last 60 lines of the newsroom pipeline
    .\scripts\gu.ps1 llm-check     can the droplet reach the 27B on this PC over Tailscale?
    .\scripts\gu.ps1 harden        firewall, fail2ban, auto security updates, SSH keys only (ASK RIC FIRST)

  Settings: $env:GU_HOST (default root@167.99.178.46), $env:GU_KEY (default ~\.ssh\id_ed25519).
  Read-only tasks are safe to schedule. deploy changes the live site; harden changes server security.
#>
param([Parameter(Mandatory = $true)][string]$Task, [string]$Ref = "", [string]$Status = "replied")
$ErrorActionPreference = "Stop"
$GuHost = if ($env:GU_HOST) { $env:GU_HOST } else { "root@167.99.178.46" }
$Key = if ($env:GU_KEY) { $env:GU_KEY } else { Join-Path $env:USERPROFILE ".ssh\id_ed25519" }
$App = "/opt/gubroadcast"
$Env = "cd $App && set -a && . ./.env && set +a"

function Remote([string]$cmd) {
    & ssh -i $Key -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new $GuHost $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "remote command exited $LASTEXITCODE" }
}

switch ($Task) {
    "ssh-test"  { Remote "echo ok: `$(hostname) `$(uptime -p)" }
    "deploy"    { Remote "cd $App && git pull -q --ff-only && sudo bash deploy/update.sh" }
    "doctor"    { Remote "sudo bash $App/deploy/doctor.sh" }
    "newsroom"  { Remote "$Env && sudo -u gbs -E .venv/bin/python -m gbs doctor" }
    "inquiries" { Remote "$Env && sudo -u gbs -E .venv/bin/python -m gbs inquiries" }
    "reply"     { if (-not $Ref) { throw "usage: gu.ps1 reply GU-YYMMDD-XXXX [-Status booked]" }
                  Remote "$Env && sudo -u gbs -E .venv/bin/python -m gbs inquiries $Ref $Status" }
    "logs"      { Remote "journalctl -u gubroadcast-pipeline -n 60 --no-pager -o cat" }
    "llm-check" { Remote "curl -s -m 8 http://100.111.143.71:11434/v1/models | head -c 400; echo" }
    "harden"    { Write-Host "This changes firewall and SSH settings on the droplet."
                  $ok = Read-Host "Type HARDEN to continue"
                  if ($ok -eq "HARDEN") { Remote "sudo bash $App/deploy/harden.sh" } }
    default     { Get-Help $PSCommandPath; exit 2 }
}
