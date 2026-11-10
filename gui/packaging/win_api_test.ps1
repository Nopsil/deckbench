# Windows 打包版 API 冒烟测试：先启动 DeckBench.exe --serve --port 18765
param([string]$Base = "http://127.0.0.1:18765", [string]$Zip = "")
$ErrorActionPreference = "Stop"
# Same PS 5.1 pitfall as smoke_api.ps1: read response bytes and decode UTF-8.
. (Join-Path $PSScriptRoot "http_utf8.ps1")
function Post($u, $o) {
  $json = $o | ConvertTo-Json -Depth 6
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  return Invoke-Utf8Json -Method POST -Uri "$Base$u" -Body $bytes -ContentType "application/json; charset=utf-8"
}
function WaitRun($rid) {
  for ($i = 0; $i -lt 600; $i++) {
    $m = Invoke-Utf8Json -Uri "$Base/api/runs/$rid"
    if ($m.status -ne 'running') { return $m }
    Start-Sleep 1
  }
  return $m
}
$c = Invoke-Utf8Json -Uri "$Base/api/catalog" -TimeoutSec 120
"catalog cards=$($c.cards.Count) agents=$(($c.agents_batch | % id) -join ',') variants=$($c.variants.Count) presets=$($c.experiments.Count) mods=$(($c.mods | % id) -join ',')"
$ra = Post "/api/runs" @{kind = "batch"; title = "WIN 基线"; params = @{char = "Claude"; asc = 0; n = 16; start = 0; procs = 8; agent = "heuristic"; variants = @(); force = @(); replace = @() } }
$ma = WaitRun $ra.id
$rb = Post "/api/runs" @{kind = "batch"; title = "WIN 加已核实+"; params = @{char = "Claude"; asc = 0; n = 16; start = 0; procs = 8; agent = "heuristic"; variants = @("hp80"); force = @("CLAUDE_VERIFIED+"); replace = @("CLAUDE_STRIKE") } }
$mb = WaitRun $rb.id
"A: $($ma.status) secs=$([int]$ma.secs) $($ma.headline | ConvertTo-Json -Compress)"
"B: $($mb.status) secs=$([int]$mb.secs) $($mb.headline | ConvertTo-Json -Compress)"
$ab = Invoke-Utf8Json -Uri "$Base/api/ab?a=$($ra.id)&b=$($rb.id)"
$ab.result.rows | % { "  AB $($_.key) A=$($_.a) B=$($_.b) diff=$($_.diff) ci=$($_.ci95) sig=$($_.significant)" }
$s = Invoke-Utf8Json -Uri "$Base/api/runs/$($rb.id)/summary"
"summary survival points=$($s.summary.survival.Count) deaths=$($s.summary.death_by_encounter.Count)"
if ($Zip) {
  # curl writes raw bytes. PS 5.1 would decode native stdout with the ANSI code page.
  $upFile = Join-Path ([IO.Path]::GetTempPath()) ("deckbench-upload-" + [guid]::NewGuid().ToString("n") + ".json")
  try {
    & curl.exe -s -o $upFile -F "file=@$Zip" "$Base/api/mods/upload"
    if ($LASTEXITCODE -ne 0) { throw "curl upload failed ($LASTEXITCODE)" }
    $up = [IO.File]::ReadAllText($upFile, (New-Object Text.UTF8Encoding $false))
    "upload: $up"
  } finally {
    if (Test-Path -LiteralPath $upFile) { Remove-Item -LiteralPath $upFile -Force }
  }
}
$rc = Post "/api/runs" @{kind = "combat"; params = @{mods = @("vanilla", "demo_mod"); decks = @("sw_start", "ironclad_start"); rooms = @("普通", "精英", "首领"); fights = 20; seed = 1; agent = "heuristic"; procs = 8; max_turns = 30 } }
$mc = WaitRun $rc.id
"combat(mod): $($mc.status) $($mc.headline | ConvertTo-Json -Compress) $($mc.error)"
$rp = Post "/api/runs" @{kind = "combat"; params = @{preset = "quick"; fights = 10; seed = 1; agent = "heuristic"; procs = 8 } }
$mp = WaitRun $rp.id
"preset: $($mp.status) $($mp.headline | ConvertTo-Json -Compress)"
$rep = Invoke-Utf8Json -Uri "$Base/api/runs/$($rp.id)/report"
"report.md chars: $($rep.markdown.Length)"
$rr = Post "/api/runs/$($ra.id)/rerun" @{}
$mr = WaitRun $rr.id
"rerun: $($mr.status) same=$(($mr.headline.avg_floor -eq $ma.headline.avg_floor))"
$rx = Post "/api/runs" @{kind = "batch"; params = @{char = "Ironclad"; asc = 10; n = 200; start = 0; procs = 2; agent = "heuristic" } }
Start-Sleep 15
Post "/api/runs/$($rx.id)/cancel" @{} | Out-Null
$mx = WaitRun $rx.id
"cancel: $($mx.status) progress=$($mx.progress | ConvertTo-Json -Compress)"
Start-Sleep 3
"history count: $((Invoke-Utf8Json -Uri "$Base/api/runs").Count)"
