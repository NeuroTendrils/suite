# Create the local Python virtualenv used by NeuroTendrils workers.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = if ($env:NEUROTENDRILS_VENV) { $env:NEUROTENDRILS_VENV } else { Join-Path $Root ".venv" }
$Requirements = Join-Path $Root "python\requirements.txt"

$Python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        $Python = $cmd.Source
        break
    }
}

if ($null -eq $Python) {
    Write-Error "python (or python3 / py) is required"
}

Write-Host "Using interpreter: $Python"
& $Python --version
Write-Host "Creating venv at: $VenvDir"

& $Python -m venv $VenvDir

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r $Requirements

Write-Host ""
Write-Host "Done. Activate with:"
Write-Host "  $VenvDir\Scripts\Activate.ps1"
Write-Host "Or let the NeuroTendrils app discover $VenvDir automatically."
