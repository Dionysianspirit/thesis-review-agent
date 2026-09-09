$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

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
$DistName = "ThesisReviewAgent"
$Entry = Join-Path $Root "python\thesis_review\gui\app.py"
$GuiData = "python\thesis_review\gui;thesis_review\gui"
$EngineData = ".vendor\docxengine\src;docxengine"

& $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name $DistName `
    --paths (Join-Path $Root "python") `
    --add-data $GuiData `
    --add-data $EngineData `
    --hidden-import thesis_review `
    --hidden-import thesis_review.gui.app `
    --hidden-import thesis_review.demo `
    --hidden-import docx `
    --collect-submodules thesis_review `
    --collect-all webview `
    $Entry

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

$BundledNode = Join-Path $RuntimeNode "node.exe"
$Selftest = Start-Process -FilePath $BundledNode -ArgumentList @((Join-Path $AgentOut "review.mjs"), "--selftest") -WorkingDirectory $AgentOut -Wait -PassThru -NoNewWindow
if ($Selftest.ExitCode -ne 0) {
    throw "Bundled pi selftest failed"
}

$Probe = Join-Path $Root "artifacts\packaged-demo"
if (Test-Path $Probe) { Remove-Item $Probe -Recurse -Force }
New-Item -ItemType Directory -Path $Probe | Out-Null
$proc = Start-Process -FilePath $Exe -ArgumentList @("--home", $Probe, "demo", "--out", $Probe) -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "Packaged demo review failed with exit $($proc.ExitCode)"
}
$Findings = $null
foreach ($i in 1..10) {
    $Findings = Get-ChildItem -Path $Probe -Filter "*-findings.json" -ErrorAction SilentlyContinue
    if ($Findings) { break }
    Start-Sleep -Milliseconds 200
}
if (-not $Findings) {
    throw "Packaged demo did not write findings.json"
}
$Gate = Join-Path $Probe "teacher-gate.json"
if (-not (Test-Path $Gate)) {
    throw "Packaged demo did not write teacher-gate.json"
}
$GatePayload = Get-Content -Path $Gate -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $GatePayload.ok) {
    throw "Packaged teacher-gate demo failed: $($GatePayload.error)"
}
if ($GatePayload.comments_before -ne 0) {
    throw "Teacher gate failed: comments were written before teacher decisions"
}
if ([int]$GatePayload.n_exported -lt 1 -or [int]$GatePayload.comments_after -lt 1) {
    throw "Packaged demo did not export teacher-approved Word comments"
}
Write-Output "Built $Exe"
Write-Output "Demo findings: $($Findings.FullName)"
Write-Output "Teacher-gate comments: $($GatePayload.comments_after) exported=$($GatePayload.n_exported)"
& $Python (Join-Path $Root "scripts\rename_dist.py")
