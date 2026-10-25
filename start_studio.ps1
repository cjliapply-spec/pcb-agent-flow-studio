param(
    [int]$Port = 8765,
    [string]$KiCadCli = "",
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonCandidates = @(
    (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
$pythonArgs = @()
if (-not $python) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $python = $pyLauncher.Source
        $pythonArgs = @("-3")
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw "Python 3.10+ not found. Install Python or create .venv." }
        $python = $pythonCommand.Source
    }
}
$commandArgs = @("server.py", "--port", [string]$Port)
if ($KiCadCli) { $commandArgs += @("--kicad-cli", $KiCadCli) }
if ($NoBrowser) { $commandArgs += "--no-browser" }
& $python @pythonArgs @commandArgs
exit $LASTEXITCODE
