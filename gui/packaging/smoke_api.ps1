# Headless smoke of the packaged DeckBench HTTP API.
# build.ps1 zips dist\DeckBench (DeckBench.exe from launcher.py, sim\ beside it).
# launcher.py calls gui.app.main. --serve is the HTTP entry and does not open a window.
#
#   powershell -ExecutionPolicy Bypass -File gui\packaging\smoke_api.ps1 -Zip <DeckBench-win64.zip> -Log <smoke.log>
#
# Extracts the zip, starts DeckBench.exe --serve, waits for GET /api/health,
# runs one training-dummy fight through POST /api/runs, then stops the process.
# The fight matches the CLI smoke (claude_v34, probe_noengine, encounter DUMMY)
# and does not need a game install. The preset file is written only into the
# extracted sim\experiments so the shipped zip and the repo stay unchanged.
param(
  [Parameter(Mandatory = $true)][string]$Zip,
  [Parameter(Mandatory = $true)][string]$Log,
  [string]$Extract = "",
  [string]$ExpectedVersion = "0.1.5",
  [int]$Port = 0,
  [int]$HealthTimeoutSec = 180,
  [int]$RunTimeoutSec = 300
)

$ErrorActionPreference = "Stop"
$script:Server = $null
$script:Packed = ""
$script:Failed = $false

function Write-Log([string]$Message) {
  $line = "{0} {1}" -f (Get-Date).ToString("o"), $Message
  [System.IO.File]::AppendAllText($Log, ($line + [Environment]::NewLine), (New-Object System.Text.UTF8Encoding $false))
  Write-Host $line
}

function Add-AppLog([string]$Packed) {
  $appLog = Join-Path $Packed "data\app.log"
  if (-not (Test-Path -LiteralPath $appLog)) {
    Write-Log "no data/app.log"
    return
  }
  Write-Log "---- data/app.log (tail) ----"
  try {
    $text = [System.IO.File]::ReadAllText($appLog)
  } catch {
    Write-Log ("app.log unreadable: {0}" -f $_.Exception.Message)
    return
  }
  $lines = @($text -split "`r?`n")
  $start = [Math]::Max(0, $lines.Length - 80)
  for ($i = $start; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -ne "") { Write-Log $lines[$i] }
  }
}

function Stop-PackagedServer {
  if (-not $script:Server) { return }
  $proc = $script:Server
  $proc.Refresh()
  if ($proc.HasExited) {
    Write-Log ("server already exited code={0}" -f $proc.ExitCode)
    return
  }
  Write-Log ("stopping server pid={0}" -f $proc.Id)
  $ErrorActionPreference = "Continue"
  & taskkill.exe /PID $proc.Id /T 2>&1 | ForEach-Object { Write-Log ("taskkill: {0}" -f $_) }
  $deadline = (Get-Date).AddSeconds(10)
  do {
    $proc.Refresh()
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 200
  } while ((Get-Date) -lt $deadline)
  $proc.Refresh()
  if (-not $proc.HasExited) {
    Write-Log "server still running; forcing stop"
    & taskkill.exe /F /T /PID $proc.Id 2>&1 | ForEach-Object { Write-Log ("taskkill: {0}" -f $_) }
    $deadline = (Get-Date).AddSeconds(15)
    do {
      $proc.Refresh()
      if ($proc.HasExited) { break }
      Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
  }
  $proc.Refresh()
  if (-not $proc.HasExited) { throw "server did not exit" }
  Write-Log ("server exited code={0}" -f $proc.ExitCode)
}

function Wait-Health([string]$Base, [int]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $last = "not tried"
  while ((Get-Date) -lt $deadline) {
    $script:Server.Refresh()
    if ($script:Server.HasExited) {
      throw ("server exited before health code={0}" -f $script:Server.ExitCode)
    }
    try {
      return Invoke-RestMethod -Uri "$Base/api/health" -TimeoutSec 5
    } catch {
      $last = $_.Exception.Message
      Start-Sleep -Seconds 1
    }
  }
  throw "GET /api/health timed out ($TimeoutSec s): $last"
}

$logParent = Split-Path -Parent $Log
if ($logParent -and -not (Test-Path -LiteralPath $logParent)) {
  New-Item -ItemType Directory -Force -Path $logParent | Out-Null
}
[System.IO.File]::WriteAllText($Log, "", (New-Object System.Text.UTF8Encoding $false))

try {
  if (-not (Test-Path -LiteralPath $Zip)) { throw "zip missing: $Zip" }
  $Zip = (Resolve-Path -LiteralPath $Zip).Path
  if (-not $Extract) {
    $Extract = Join-Path (Split-Path -Parent $Zip) "api-smoke-extract"
  }
  if (Test-Path -LiteralPath $Extract) { Remove-Item -LiteralPath $Extract -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $Extract | Out-Null
  Write-Log "extract $Zip -> $Extract"
  Expand-Archive -LiteralPath $Zip -DestinationPath $Extract
  $script:Packed = Join-Path $Extract "DeckBench"
  $exe = Join-Path $script:Packed "DeckBench.exe"
  if (-not (Test-Path -LiteralPath $exe)) { throw "zip is missing DeckBench.exe" }
  $expDir = Join-Path $script:Packed "sim\experiments"
  if (-not (Test-Path -LiteralPath $expDir)) { throw "zip is missing sim/experiments" }
  $preset = Join-Path $expDir "api_smoke.yaml"
  @(
    "name: api_smoke"
    "title: packaged api smoke"
    "mods: [claude_v34]"
    "seed: 1"
    "fights: 1"
    "max_turns: 1"
    "agent: heuristic"
    "decks: []"
    "extra:"
    "  - {deck: probe_noengine, encounter: DUMMY, fights: 1, max_turns: 1, room: probe}"
  ) | Set-Content -LiteralPath $preset -Encoding ascii
  Write-Log "wrote extracted preset $preset"

  if ($Port -le 0) {
    $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $Port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    $listener.Stop()
  }
  foreach ($name in @(
      "PYTHONPATH", "DECKBENCH_SIM", "DECKBENCH_GAME_DIR", "DECKBENCH_CODEX_DIR",
      "DECKBENCH_EXPLAIN", "STS2SIM_ROOT", "STS2SIM_GUI_DATA", "STS2SIM_USER_MODS",
      "DECKBENCH_CACHE", "DECKBENCH_ILSPY")) {
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
  }
  $env:DECKBENCH_NO_DIALOG = "1"
  Write-Log "start $exe --serve --port $Port"
  $script:Server = Start-Process -FilePath $exe -ArgumentList "--serve --port $Port" `
    -WorkingDirectory $script:Packed -PassThru -WindowStyle Hidden
  Write-Log ("server pid={0}" -f $script:Server.Id)

  $base = "http://127.0.0.1:$Port"
  $health = Wait-Health $base $HealthTimeoutSec
  Write-Log ("health " + ($health | ConvertTo-Json -Compress -Depth 4))
  if (-not $health.ok) { throw "health ok is not true" }
  if ([string]$health.version -ne $ExpectedVersion) {
    throw "health version '$($health.version)' != '$ExpectedVersion'"
  }
  if ($health.frozen -ne $true) { throw "health frozen is not true" }

  $bodyObj = @{
    kind = "combat"
    title = "api smoke"
    params = @{
      preset = "api_smoke"
      fights = 1
      seed = 1
      agent = "heuristic"
      procs = 1
    }
  }
  $body = $bodyObj | ConvertTo-Json -Depth 6 -Compress
  Write-Log "POST /api/runs $body"
  $started = Invoke-RestMethod -Method Post -Uri "$base/api/runs" `
    -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
    -ContentType "application/json; charset=utf-8" -TimeoutSec 60
  if (-not $started.id) { throw "POST /api/runs returned no id" }
  Write-Log ("run id={0}" -f $started.id)

  $meta = $null
  $deadline = (Get-Date).AddSeconds($RunTimeoutSec)
  do {
    $script:Server.Refresh()
    if ($script:Server.HasExited) {
      throw ("server exited during the run code={0}" -f $script:Server.ExitCode)
    }
    $meta = Invoke-RestMethod -Uri "$base/api/runs/$($started.id)" -TimeoutSec 30
    if ($meta.status -ne "running" -and $meta.status -ne "queued") { break }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  Write-Log ("run status={0} error={1}" -f $meta.status, $meta.error)
  if ($meta.status -eq "running" -or $meta.status -eq "queued") {
    throw "run timed out after $RunTimeoutSec s"
  }
  if ($meta.status -ne "done") {
    try {
      $runLog = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/runs/$($started.id)/files/run.log" -TimeoutSec 30
      Write-Log "---- run.log ----"
      Write-Log ([string]$runLog.Content)
    } catch {
      Write-Log ("run.log unavailable: {0}" -f $_.Exception.Message)
    }
    throw "run status $($meta.status)"
  }

  $rawResp = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/runs/$($started.id)/files/raw.jsonl" -TimeoutSec 30
  $raw = [string]$rawResp.Content
  Write-Log ("raw.jsonl " + $raw.Trim())
  if ($raw -notmatch '"encounter": "DUMMY"') { throw "smoke fight was not the training dummy" }
  if ($raw -notmatch '"deck": "probe_noengine"') { throw "smoke fight did not use the packaged probe deck" }
  $summary = Invoke-RestMethod -Uri "$base/api/runs/$($started.id)/summary" -TimeoutSec 30
  Write-Log ("summary " + ($summary.summary | ConvertTo-Json -Compress -Depth 4))
  $fights = 0
  if ($summary.summary -and $null -ne $summary.summary.fights) { $fights = [int]$summary.summary.fights }
  if ($fights -lt 1) { throw "summary fights=$fights" }
  Write-Log "PASS"
} catch {
  $script:Failed = $true
  Write-Log ("FAIL: {0}" -f $_.Exception.Message)
  if ($_.ScriptStackTrace) { Write-Log $_.ScriptStackTrace }
} finally {
  if ($script:Packed) { Add-AppLog $script:Packed }
  try {
    Stop-PackagedServer
  } catch {
    Write-Log ("stop failed: {0}" -f $_.Exception.Message)
    $script:Failed = $true
  }
}

if ($script:Failed) { exit 1 }
exit 0
