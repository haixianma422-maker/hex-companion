$ErrorActionPreference = 'Stop'
$companionPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$companionApp = Join-Path $PSScriptRoot 'app.py'
if (-not (Test-Path -LiteralPath $companionPython)) {
    throw 'Please run setup_demo.cmd first.'
}
# Run only this companion with UAC consent; do not alter League or security settings.
Start-Process -FilePath $companionPython -ArgumentList ('"{0}"' -f $companionApp) -WorkingDirectory $PSScriptRoot -Verb RunAs -WindowStyle Hidden
