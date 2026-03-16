$ErrorActionPreference = "Stop"

$packageName = "adanos-cli"

function Write-Info($message) {
    Write-Host $message
}

function Get-PythonCommand {
    foreach ($candidate in @("py", "python", "python3")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    throw "Python is required. Install Python 3.10+ and re-run this script."
}

$python = Get-PythonCommand
$pipx = Get-Command pipx -ErrorAction SilentlyContinue

if (-not $pipx) {
    Write-Info "Installing pipx..."
    & $python -m pip install --user --upgrade pip pipx
    & $python -m pipx ensurepath | Out-Null
}

$pipx = Get-Command pipx -ErrorAction SilentlyContinue

if ($pipx) {
    Write-Info "Installing $packageName with pipx..."
    & $pipx.Source install --force $packageName
} else {
    Write-Info "pipx is not available in the current session. Falling back to pip --user."
    & $python -m pip install --user --upgrade $packageName
}

Write-Info ""
Write-Info "Installed $packageName."
Write-Info "Verify with:"
Write-Info "  adanos --version"
