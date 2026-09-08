$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "先创建 .venv 并安装 requirements.txt"
}
$env:PYTHONPATH = Join-Path $Root "python"
& $Python -m thesis_review.gui.app @args
