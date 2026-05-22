$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path .venv)) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
python -m craftsman.cli serve
