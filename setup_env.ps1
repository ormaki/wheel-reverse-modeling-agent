param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Resolve-Python {
    param([string]$RequestedPython)

    if ($RequestedPython) {
        return $RequestedPython
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $resolved = & py -3.10 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                return $resolved.Trim()
            }
        } catch {
        }
    }

    return "python"
}

$python = Resolve-Python -RequestedPython $PythonExe
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

Write-Host "Using Python interpreter: $python"

if (-not (Test-Path $venvPython)) {
    & $python -m venv .venv
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install --prefer-binary -r requirements.txt

Write-Host ""
Write-Host "Environment ready."
Write-Host "Preview command:"
Write-Host "  .\.venv\Scripts\python.exe -X utf8 stl_to_step_pipeline.py input/wheel.stl --preview-only --no-preview-window"
Write-Host "Headless full run:"
Write-Host "  .\.venv\Scripts\python.exe -X utf8 stl_to_step_pipeline.py input/wheel.stl --auto-confirm --no-preview-window"
