# DeckBench Windows 打包（PyInstaller onedir + 自带反编译器）。在仓库根目录或任意位置运行：
#   powershell -ExecutionPolicy Bypass -File gui\packaging\build.ps1 -Work "D:\build\deckbench" -Py "<venv>\Scripts\python.exe" -Decompiler "<ilspycmd-host 发布目录>"
# 只打包 git 跟踪的文件（不会带上本机生成的游戏数据）；构建后请运行 audit.ps1 检查。
param(
  [string]$Work = "",
  [string]$Py = "",
  [string]$Decompiler = "",
  [string]$Version = "0.1.2"
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Work) { $Work = Join-Path (Split-Path $Repo -Parent) "build-work" }
if (-not $Py) { $Py = Join-Path $Work "buildenv\Scripts\python.exe" }
New-Item -ItemType Directory -Force $Work | Out-Null
# 临时文件、npm 缓存、PyInstaller 缓存都放到工作目录（避免占用 C 盘）
$tmp = Join-Path $Work "tmp"; New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TEMP = $tmp; $env:TMP = $tmp
$env:npm_config_cache = Join-Path $Work ".npmcache"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Work ".pyinstaller"

Write-Host "[1/5] 前端构建 / building web UI"
Push-Location (Join-Path $Repo "gui\web")
& npm.cmd ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
& npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw "npm run build 失败" }
Pop-Location

Write-Host "[2/5] 暂存源码（只取 git 跟踪的文件）/ staging tracked files only"
$stage = Join-Path $Work "stage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
$src = Join-Path $stage "src"; $sim = Join-Path $stage "sim"
New-Item -ItemType Directory -Force $src, $sim | Out-Null
$files = & git -C $Repo ls-files
foreach ($f in $files) {
  $rel = $f -replace '/', '\'
  if ($f -match '^(sts2sim|mods|tools|data|experiments)/') { $dst = Join-Path $sim $rel }
  elseif ($f -match '^gui/' -and $f -notmatch '^gui/(packaging|web)/') { $dst = Join-Path $src $rel }
  else { continue }
  New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
  Copy-Item (Join-Path $Repo $rel) $dst
}
Copy-Item -Recurse (Join-Path $Repo "gui\web\dist") (Join-Path $src "gui\web\dist")
foreach ($f in "launcher.py", "DeckBench.spec", "icon.ico") { Copy-Item (Join-Path $PSScriptRoot $f) $src }

Write-Host "[3/5] PyInstaller"
$dist = Join-Path $Work "dist"
Push-Location $src
& $Py -m PyInstaller --noconfirm --distpath $dist --workpath (Join-Path $Work "pyi-work") DeckBench.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }
Pop-Location

Write-Host "[4/5] 组装 / assembling"
$app = Join-Path $dist "DeckBench"
Copy-Item -Recurse $sim (Join-Path $app "sim")
if ($Decompiler) {
  if (-not (Test-Path (Join-Path $Decompiler "ilspycmd-host.exe"))) { throw "反编译器目录里没有 ilspycmd-host.exe: $Decompiler" }
  Copy-Item -Recurse $Decompiler (Join-Path $app "decompiler")
} else { Write-Warning "没有 -Decompiler：玩家需要自己安装 .NET 9 SDK + ilspycmd" }
# pythonnet（独立窗口用）在部分机器上把非系统盘的 DLL 当成「远程来源」拒绝加载：给 exe 配上 loadFromRemoteSources
$cfg = '<?xml version="1.0" encoding="utf-8"?><configuration><runtime><loadFromRemoteSources enabled="true"/></runtime></configuration>'
[IO.File]::WriteAllText((Join-Path $app "DeckBench.exe.config"), $cfg, (New-Object Text.UTF8Encoding $false))
Copy-Item (Join-Path $Repo "LICENSE") (Join-Path $app "LICENSE.txt")
Copy-Item (Join-Path $PSScriptRoot "README-win.txt") (Join-Path $app "README.txt")
Copy-Item (Join-Path $PSScriptRoot "THIRD-PARTY-NOTICES.txt") $app
Copy-Item -Recurse (Join-Path $PSScriptRoot "notices") (Join-Path $app "notices")
Set-Content -Encoding ascii (Join-Path $app "VERSION.txt") $Version

Write-Host "[5/5] 压缩 / zipping"
$zip = Join-Path $Work "DeckBench-$Version-win64.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $app -DestinationPath $zip -CompressionLevel Optimal
Write-Host "完成 / done: $app"
Write-Host "zip: $zip"
