$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv/Scripts/python.exe')) { python -m venv .venv }
$tgtopPython = Join-Path (Get-Location) '.venv/Scripts/python.exe'
& $tgtopPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $tgtopPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
node scripts/account-ui-smoke.cjs
if ($LASTEXITCODE -ne 0) { throw 'UI account isolation checks failed' }
node scripts/cloud-connection-smoke.cjs
if ($LASTEXITCODE -ne 0) { throw 'Cloud connection checks failed' }
& $tgtopPython -m PyInstaller --noconfirm --clean --onedir --name tgtop-server --add-data 'web;web' --collect-all twilio --collect-all openai run.py
if ($LASTEXITCODE -ne 0) { throw 'Backend packaging failed' }
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed' }
node scripts/package-photon.cjs
if ($LASTEXITCODE -ne 0) { throw 'Photon runtime packaging failed' }
$env:ELECTRON_BUILDER_CACHE = Join-Path (Get-Location) 'runtime/builder-cache'
npm run package
if ($LASTEXITCODE -ne 0) { throw 'Installer packaging failed' }
