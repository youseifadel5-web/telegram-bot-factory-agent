$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Write-Host '== Windows OpenCode bootstrap =='
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"

node --version
npm --version

# OpenCode is installed for the current runner only; no Docker or persistent service is used.
npm install --global opencode-ai

Write-Host 'OpenCode version:'
opencode --version

# Lightweight repository tools available on the hosted Windows image.
git --version
python --version

if ($env:OPENCODE_API_KEY) {
    Write-Host 'OPENCODE_API_KEY is present as a masked environment variable.'
} else {
    Write-Host 'No provider key was supplied; OpenCode installation is complete, but model calls need a GitHub Secret.'
}
