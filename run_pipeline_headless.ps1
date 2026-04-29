param(
    [string]$InputStl = "input/wheel.stl",
    [string]$OutputStep = "",
    [switch]$DisableSpokes
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

$cmd = @(
    "-X", "utf8",
    "stl_to_step_pipeline.py",
    $InputStl,
    "--auto-confirm",
    "--no-preview-window"
)

if ($OutputStep) {
    $cmd += @("--output-step", $OutputStep)
}

if ($DisableSpokes) {
    $cmd += "--disable-spokes"
}

& $python @cmd
