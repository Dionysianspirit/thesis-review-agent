$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    python -m venv .venv
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    & $Python -m pip install -U pip
    & $Python -m pip install -r requirements.txt
}

& $Python (Join-Path $Root "scripts\fetch_docxengine.py")
& $Python (Join-Path $Root "scripts\fetch_node.py")
Push-Location (Join-Path $Root "agent")
npm ci --omit=dev
Pop-Location

# PyInstaller gets an ASCII name; Python then renames the folder/exe to 论文审改助手.
# Freeze flags live in scripts/pyinstaller_build.py so Windows and Linux smoke stay in sync.
$DistName = "ThesisReviewAgent"
& $Python (Join-Path $Root "scripts\pyinstaller_build.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller freeze failed with exit $LASTEXITCODE"
}

$OutDir = Join-Path $Root "dist\$DistName"
$Exe = Join-Path $OutDir "$DistName.exe"
if (-not (Test-Path $Exe)) {
    throw "Build did not produce $Exe"
}

$RuntimeNode = Join-Path $OutDir "runtime\node"
New-Item -ItemType Directory -Force -Path $RuntimeNode | Out-Null
Copy-Item -Path (Join-Path $Root ".vendor\node\*") -Destination $RuntimeNode -Recurse -Force
$AgentOut = Join-Path $OutDir "agent"
if (Test-Path $AgentOut) { Remove-Item $AgentOut -Recurse -Force }
Copy-Item -Path (Join-Path $Root "agent") -Destination $AgentOut -Recurse -Force

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
# rename_dist.py prints the product exe path; do not put that Chinese path in a
# PowerShell quoted string (encoding can unbalance quotes at parse time).
$RenameOut = & $Python (Join-Path $Root "scripts\rename_dist.py")
if ($LASTEXITCODE -ne 0) {
    throw "rename_dist.py failed with exit $LASTEXITCODE"
}
$ProductExe = ($RenameOut | Select-Object -Last 1).ToString().Trim()
if (-not (Test-Path $ProductExe)) {
    throw "rename_dist.py did not print a product exe path"
}
$ProductDir = Split-Path -Parent $ProductExe
Write-Output $ProductExe
$Smoke = Join-Path $Root "scripts\smoke_packaged_demo.py"
& $Python $Smoke --dist $ProductDir
if ($LASTEXITCODE -ne 0) {
    throw "Frozen teacher EXE smoke failed with exit $LASTEXITCODE"
}
