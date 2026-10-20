# 在构建目录（含 src\、sim\、buildenv\）里运行：powershell -ExecutionPolicy Bypass -File src\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = Join-Path $root "buildenv\Scripts\python.exe"
Set-Location (Join-Path $root "src")
& $py -m PyInstaller --noconfirm --distpath (Join-Path $root "dist") --workpath (Join-Path $root "build") DeckBench.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }
$app = Join-Path $root "dist\DeckBench"
$simDst = Join-Path $app "sim"
if (Test-Path $simDst) { Remove-Item -Recurse -Force $simDst }
Copy-Item -Recurse (Join-Path $root "sim") $simDst
# pythonnet（独立窗口用）在部分机器上把 D: 盘的 DLL 当成「远程来源」拒绝加载：给 exe 配上 loadFromRemoteSources
$cfg = '<?xml version="1.0" encoding="utf-8"?><configuration><runtime><loadFromRemoteSources enabled="true"/></runtime></configuration>'
[IO.File]::WriteAllText((Join-Path $app "DeckBench.exe.config"), $cfg, (New-Object Text.UTF8Encoding $false))
Write-Host "完成：$app\DeckBench.exe"
