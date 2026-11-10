# Headless smoke of the packaged DeckBench HTTP API.
# build.ps1 zips dist\DeckBench (DeckBench.exe from launcher.py, sim\ beside it).
# launcher.py calls gui.app.main. --serve is the HTTP entry and does not open a window.
#
#   powershell -ExecutionPolicy Bypass -File gui\packaging\smoke_api.ps1 -Zip <DeckBench-win64.zip> -Log <smoke.log>
#
# Extracts the zip, starts DeckBench.exe --serve, waits for GET /api/health,
# checks GET /api/version against that version, VERSION.txt, and the exe
# file version, runs one training-dummy fight through POST /api/runs, then
# stops the process.
# The fight matches the CLI smoke (claude_v34, probe_noengine, encounter DUMMY)
# and does not need a game install. The preset file is written only into the
# extracted sim\experiments so the shipped zip and the repo stay unchanged.
# HTTP bodies are read as bytes and decoded as UTF-8. Windows PowerShell 5.1
# otherwise uses ISO-8859-1 when Content-Type has no charset. JSON responses
# must send charset=utf-8. DUMMY enc_name must survive that round trip.
# This file stays pure ASCII; the expected name is code points, not a literal.
param(
  [Parameter(Mandatory = $true)][string]$Zip,
  [Parameter(Mandatory = $true)][string]$Log,
  [string]$Extract = "",
  [string]$ExpectedVersion = "",
  [int]$Port = 0,
  [int]$HealthTimeoutSec = 180,
  [int]$RunTimeoutSec = 300
)

$ErrorActionPreference = "Stop"
$script:Server = $null
$script:Packed = ""
$script:DataDir = ""
$script:Failed = $false
$script:Utf8 = [System.Text.UTF8Encoding]::new($false)
# DUMMY enc_name is U+6728 U+6869 (the training dummy). Code points keep this file ASCII.
$script:DummyEncName = -join @([char]0x6728, [char]0x6869)
. (Join-Path $PSScriptRoot "http_utf8.ps1")

function Format-CodePoints([string]$Value) {
  if ([string]::IsNullOrEmpty($Value)) { return "<empty>" }
  return (($Value.ToCharArray() | ForEach-Object { "U+{0:X4}" -f [int]$_ }) -join " ")
}

function Test-HasCjk([string]$Value) {
  if ([string]::IsNullOrEmpty($Value)) { return $false }
  foreach ($ch in $Value.ToCharArray()) {
    $n = [int]$ch
    if ($n -ge 0x4E00 -and $n -le 0x9FFF) { return $true }
  }
  return $false
}

function Convert-FightLines([string]$Text) {
  # Keep the list in script scope. Returning it from a function makes
  # Windows PowerShell 5.1 unwrap a one-element array.
  $script:FightLines = @()
  foreach ($fightLine in ($Text -split "[\r\n]+")) {
    $fightLine = $fightLine.Trim()
    if ($fightLine -eq "") { continue }
    $script:FightLines += ,($fightLine | ConvertFrom-Json)
  }
}

function Test-VersionMatch([string]$Got, [string]$Want) {
  if ([string]::IsNullOrEmpty($Got) -or [string]::IsNullOrEmpty($Want)) { return $false }
  if ($Got -eq $Want) { return $true }
  if ($Got -eq ($Want + ".0")) { return $true }
  return $false
}

function Write-Log([string]$Message) {
  $line = "{0} {1}" -f (Get-Date).ToString("o"), $Message
  [System.IO.File]::AppendAllText($Log, ($line + [Environment]::NewLine), $script:Utf8)
  Write-Host $line
}

function Read-SharedUtf8([string]$Path) {
  # The server keeps app.log open for the whole process. ReadAllText shares
  # nothing and fails with "used by another process". ReadWrite lets us tail it.
  $fs = $null
  $reader = $null
  try {
    $fs = New-Object System.IO.FileStream(
      $Path,
      [System.IO.FileMode]::Open,
      [System.IO.FileAccess]::Read,
      [System.IO.FileShare]::ReadWrite)
    $reader = New-Object System.IO.StreamReader($fs, $script:Utf8)
    return $reader.ReadToEnd()
  } finally {
    if ($null -ne $reader) { $reader.Dispose() }
    elseif ($null -ne $fs) { $fs.Dispose() }
  }
}

function Add-AppLog([string]$Packed) {
  $appLog = Join-Path $Packed "data\app.log"
  if ($script:DataDir) { $appLog = Join-Path $script:DataDir "app.log" }
  if (-not (Test-Path -LiteralPath $appLog)) {
    Write-Log "no data/app.log"
    return
  }
  Write-Log "---- data/app.log (tail) ----"
  try {
    $text = Read-SharedUtf8 $appLog
  } catch {
    Write-Log ("app.log unreadable: {0}" -f $_.Exception.Message)
    return
  }
  $lines = @(($text -replace "`r`n", "`n") -split "`n")
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
  # DeckBench.exe has no HTTP shutdown route. /F /T is the stop.
  # taskkill's own exit code, and the killed process code, are not a smoke failure.
  Write-Log ("stopping server pid={0}" -f $proc.Id)
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = Join-Path $env:SystemRoot "System32\taskkill.exe"
  $psi.Arguments = "/F /T /PID $($proc.Id)"
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $killer = [System.Diagnostics.Process]::Start($psi)
  $null = $killer.WaitForExit()
  $killCode = $killer.ExitCode
  $killer.Dispose()
  $proc.Refresh()
  if (-not $proc.HasExited) {
    Start-Sleep -Milliseconds 500
    $proc.Refresh()
  }
  if (-not $proc.HasExited) { throw "server did not exit" }
  Write-Log ("server stopped (taskkill exit={0}, process code={1})" -f $killCode, $proc.ExitCode)
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
      return Invoke-Utf8Json -Uri "$Base/api/health" -TimeoutSec 5
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
[System.IO.File]::WriteAllText($Log, "", $script:Utf8)

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
  $versionTxt = Join-Path $script:Packed "VERSION.txt"
  if (-not (Test-Path -LiteralPath $versionTxt)) { throw "VERSION.txt missing" }
  $stamped = ([System.IO.File]::ReadAllText($versionTxt)).Trim()
  if (-not $stamped) { throw "VERSION.txt is empty" }
  if (-not $ExpectedVersion) { $ExpectedVersion = $stamped }
  if ($stamped -ne $ExpectedVersion) {
    throw "VERSION.txt '$stamped' != expected '$ExpectedVersion'"
  }
  $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($exe)
  Write-Log ("exe ProductVersion={0} FileVersion={1}" -f $info.ProductVersion, $info.FileVersion)
  if (-not (Test-VersionMatch ([string]$info.ProductVersion) $ExpectedVersion)) {
    throw "exe ProductVersion '$($info.ProductVersion)' != '$ExpectedVersion'"
  }
  if (-not (Test-VersionMatch ([string]$info.FileVersion) $ExpectedVersion)) {
    throw "exe FileVersion '$($info.FileVersion)' != '$ExpectedVersion'"
  }
  $decompiler = Join-Path $script:Packed "decompiler\ilspycmd-host.exe"
  if (Test-Path -LiteralPath $decompiler) {
    $dinfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($decompiler)
    Write-Log ("decompiler ProductVersion={0} FileVersion={1}" -f $dinfo.ProductVersion, $dinfo.FileVersion)
    $productOk = Test-VersionMatch ([string]$dinfo.ProductVersion) $ExpectedVersion
    $fileOk = Test-VersionMatch ([string]$dinfo.FileVersion) $ExpectedVersion
    if (-not $productOk -and -not $fileOk) {
      throw "decompiler file version does not match '$ExpectedVersion'"
    }
  }
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
  $script:DataDir = [string]$health.data_dir
  if (-not $script:DataDir) { throw "health did not report data_dir" }
  Write-Log ("health " + ($health | ConvertTo-Json -Compress -Depth 4))
  if (-not $health.ok) { throw "health ok is not true" }
  if ([string]$health.version -ne $ExpectedVersion) {
    throw "health version '$($health.version)' != '$ExpectedVersion'"
  }
  if ($health.frozen -ne $true) { throw "health frozen is not true" }

  $reported = Invoke-Utf8Json -Uri "$base/api/version" -TimeoutSec 15
  Write-Log ("version " + ($reported | ConvertTo-Json -Compress -Depth 4))
  if ([string]$reported.name -ne "DeckBench") { throw "GET /api/version name is not DeckBench" }
  if ([string]$reported.version -ne $ExpectedVersion) {
    throw "GET /api/version '$($reported.version)' != '$ExpectedVersion'"
  }
  if ([string]$reported.version -ne [string]$health.version) {
    throw "GET /api/version does not match GET /api/health"
  }

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
  $started = Invoke-Utf8Json -Method POST -Uri "$base/api/runs" `
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
    $meta = Invoke-Utf8Json -Uri "$base/api/runs/$($started.id)" -TimeoutSec 30
    if ($meta.status -ne "running" -and $meta.status -ne "queued") { break }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  Write-Log ("run status={0} error={1}" -f $meta.status, $meta.error)
  if ($meta.status -eq "running" -or $meta.status -eq "queued") {
    throw "run timed out after $RunTimeoutSec s"
  }
  if ($meta.status -ne "done") {
    $runLogPath = Join-Path $script:DataDir ("runs\{0}\run.log" -f $started.id)
    if (Test-Path -LiteralPath $runLogPath) {
      Write-Log "---- run.log ----"
      Write-Log (Read-SharedUtf8 $runLogPath)
    } else {
      Write-Log "run.log missing: $runLogPath"
    }
    throw "run status $($meta.status)"
  }

  # The file on disk is the simulator's own UTF-8. The HTTP body is decoded
  # from bytes below; do not cast those bytes through a string (PS 5.1 prints
  # them as "123 34 100 ...").
  $rawPath = Join-Path $script:DataDir ("runs\{0}\out\raw.jsonl" -f $started.id)
  if (-not (Test-Path -LiteralPath $rawPath)) { throw "raw.jsonl missing: $rawPath" }
  $rawText = [System.IO.File]::ReadAllText($rawPath, $script:Utf8).Trim()
  Write-Log ("raw.jsonl " + $rawText)
  Convert-FightLines $rawText
  $parsed = $script:FightLines
  if ($parsed.Count -lt 1) { throw "raw.jsonl had no fight" }
  $fight = $parsed[0]
  Write-Log ("fight deck={0} encounter={1} result={2} turns={3}" -f $fight.deck, $fight.encounter, $fight.result, $fight.turns)
  if ([string]$fight.encounter -ne "DUMMY") {
    throw ("smoke fight was not the training dummy (encounter={0})" -f $fight.encounter)
  }
  if ([string]$fight.deck -ne "probe_noengine") {
    throw ("smoke fight did not use the packaged probe deck (deck={0})" -f $fight.deck)
  }

  $rawUri = "$base/api/runs/$($started.id)/files/raw.jsonl"
  $rawHttp = Get-Utf8Response -Uri $rawUri -TimeoutSec 30
  Write-Log ("raw.jsonl http content-type={0} bytes={1}" -f $rawHttp.ContentType, $rawHttp.Bytes)
  Convert-FightLines ([string]$rawHttp.Text)
  $httpFights = $script:FightLines
  if ($httpFights.Count -lt 1) { throw "HTTP raw.jsonl had no fight" }
  $httpFight = $httpFights[0]
  $gotName = [string]$httpFight.enc_name
  Write-Log ("HTTP enc_name code points {0}" -f (Format-CodePoints $gotName))
  if ($gotName -ne $script:DummyEncName) {
    throw ("DUMMY enc_name did not round-trip (got {0})" -f (Format-CodePoints $gotName))
  }
  if ($gotName -ne [string]$fight.enc_name) {
    throw "HTTP enc_name does not match raw.jsonl on disk"
  }
  if ([string]$httpFight.encounter -ne "DUMMY") {
    throw ("HTTP fight was not the training dummy (encounter={0})" -f $httpFight.encounter)
  }

  $summaryUri = "$base/api/runs/$($started.id)/summary"
  $summaryGot = Get-Utf8Response -Uri $summaryUri -TimeoutSec 30
  Write-Log ("summary content-type={0}" -f $summaryGot.ContentType)
  $summary = ConvertFrom-Utf8Response -Response $summaryGot -Uri $summaryUri
  Write-Log ("summary " + ($summary.summary | ConvertTo-Json -Compress -Depth 4))
  $fights = 0
  if ($summary.summary -and $null -ne $summary.summary.fights) { $fights = [int]$summary.summary.fights }
  if ($fights -lt 1) { throw "summary fights=$fights" }
  $decks = @()
  if ($summary.summary -and $null -ne $summary.summary.cells) {
    $decks = @($summary.summary.cells | ForEach-Object { [string]$_.deck })
  }
  $sawCjk = $false
  foreach ($deckName in $decks) {
    if (Test-HasCjk $deckName) { $sawCjk = $true }
  }
  if (-not $sawCjk) {
    $shown = ($decks | ForEach-Object { Format-CodePoints $_ }) -join "; "
    throw "summary deck name was not UTF-8 Chinese ($shown)"
  }
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
