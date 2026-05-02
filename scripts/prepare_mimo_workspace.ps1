$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$inputDir = Join-Path $repoRoot "input"
$readonlyDir = Join-Path $repoRoot "input_readonly"
$outputMimoDir = Join-Path $repoRoot "output_mimo"
$experimentsDir = Join-Path $repoRoot "experiments"

New-Item -ItemType Directory -Path $readonlyDir -Force | Out-Null
New-Item -ItemType Directory -Path $outputMimoDir -Force | Out-Null
New-Item -ItemType Directory -Path $experimentsDir -Force | Out-Null

$sourceWheel = Join-Path $inputDir "wheel.stl"
$readonlyWheel = Join-Path $readonlyDir "wheel.stl"

if (Test-Path -LiteralPath $sourceWheel) {
    Copy-Item -LiteralPath $sourceWheel -Destination $readonlyWheel -Force
    Set-ItemProperty -LiteralPath $readonlyWheel -Name IsReadOnly -Value $true
    Write-Output "Created read-only input copy: $readonlyWheel"
} else {
    Write-Output "input/wheel.stl not found. Restore replication assets before running modeling tasks."
}

Write-Output "Prepared MiMo Claw workspace:"
Write-Output "  input_readonly/: protected input copy"
Write-Output "  output_mimo/: generated MiMo outputs"
Write-Output "  experiments/: isolated experiments"
