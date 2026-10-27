# 发布前审计：确认打包目录 / zip 里没有任何游戏文件、游戏数据或生成的游戏代码。
#   powershell -ExecutionPolicy Bypass -File gui\packaging\audit.ps1 -Path <dist\DeckBench 或 .zip> [-GameDir <游戏安装目录>] [-Cache <本机生成缓存目录>...]
# 任何一项命中都以退出码 1 结束。
param([Parameter(Mandatory = $true)][string]$Path, [string]$GameDir = "", [string[]]$Cache = @())
$ErrorActionPreference = "Stop"
$root = $Path
if ($Path -like "*.zip") {
  $root = Join-Path ([IO.Path]::GetDirectoryName((Resolve-Path $Path))) ("audit-" + [IO.Path]::GetFileNameWithoutExtension($Path))
  if (Test-Path $root) { Remove-Item -Recurse -Force $root }
  Expand-Archive $Path $root
}
$all = Get-ChildItem -Recurse -File $root
$bad = New-Object System.Collections.ArrayList
function Hit($what, $f) { [void]$bad.Add("$what :: $($f.FullName.Substring($root.Length))") }

# 1) 文件名黑名单：生成的游戏代码 / 游戏数据 / 游戏二进制 / 反编译源码 / 缓存标记
$names = @('game.py', 'game_report.json', 'game_report_skipped.tsv', 'undefined.txt', 'monster_ai.json', 'encounter_monsters.json',
  'sts2.dll', 'sts2.pdb', 'sts2.deps.json', 'sts2.runtimeconfig.json', 'release_info.json', 'GodotSharp.dll', '0Harmony.dll',
  'manifest.json', 'DO_NOT_REDISTRIBUTE.txt', 'current.json')
foreach ($f in $all) {
  if ($names -contains $f.Name) { Hit "forbidden name" $f }
  if ($f.Extension -in '.pck', '.cs', '.csproj', '.onnx') { Hit "forbidden type $($f.Extension)" $f }
  if ($f.Name -eq 'champions.toml') { Hit "spire-mentor ppo config" $f }
  if ($f.FullName -match '[\\/]sts2_rs[\\/]|[\\/]sts2_hint[\\/]') { Hit "spire-mentor package" $f }
  if ($f.Name -match '^(eng|zhs)_(cards|monsters|relics|powers|potions|encounters|characters|acts)\.json$') { Hit "spire-codex data" $f }
  if ($f.FullName -match '\\(spire-codex|sts2-beta-src|sts2-src|decompiled|stubs|legacy|vanilla|testcache|deckbench\\[0-9a-f]{16})\\') { Hit "forbidden folder" $f }
}
# 2) 内容：反编译 C# / 大段转译代码的特征（只查文本类文件）
$text = $all | Where-Object { $_.Extension -in '.py', '.json', '.txt', '.yaml', '.yml', '.md', '.tsv', '.js', '.html' -and $_.Length -lt 20MB }
foreach ($f in $text) {
  $c = [IO.File]::ReadAllText($f.FullName)
  if ($c -match 'namespace MegaCrit\.Sts2|using MegaCrit\.Sts2') { Hit "decompiled C# marker" $f }
  if ($f.Extension -eq '.py' -and $f.Length -gt 400KB) { Hit "suspiciously large .py (generated?)" $f }
  if ($c -match 'class [A-Za-z]+\(CardModel\)|class [A-Za-z]+\(MonsterModel\)') { Hit "transpiled game class" $f }
}
# 3) 和真实游戏安装 / 本机缓存逐文件比对哈希
$ref = @{}
foreach ($d in @($GameDir) + $Cache) {
  if ($d -and (Test-Path $d)) {
    Get-ChildItem -Recurse -File $d -ErrorAction SilentlyContinue | Where-Object { $_.Length -lt 200MB -and $_.Length -gt 0 } |
      ForEach-Object { $ref[(Get-FileHash -Algorithm SHA256 $_.FullName).Hash] = $_.FullName }
  }
}
if ($ref.Count) {
  foreach ($f in $all) { $h = (Get-FileHash -Algorithm SHA256 $f.FullName).Hash; if ($ref.ContainsKey($h)) { Hit "identical to $($ref[$h])" $f } }
}
"checked $($all.Count) files in $root; reference hashes: $($ref.Count)"
if ($bad.Count) { "FAIL ($($bad.Count))"; $bad | Select-Object -First 50; exit 1 } else { "PASS: no game files, game data or generated game code found" }
