$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$craftsmanRoot = Join-Path $repoRoot "craftsman"
$systemdUnit = Join-Path $repoRoot "docker\systemd\craftsman.service"
$systemdEnv = Join-Path $repoRoot "docker\systemd\craftsman.env.example"
$nginxConf = Join-Path $repoRoot "docker\nginx\craftsman.conf.example"

$checks = @()

function Add-Check($name, $ok, $detail) {
    $script:checks += [pscustomobject]@{
        name = $name
        ok = $ok
        detail = $detail
    }
}

try {
    $python = python --version 2>&1
    Add-Check "python" $true $python
} catch {
    Add-Check "python" $false "python not found"
}

Add-Check "craftsman-root" (Test-Path $craftsmanRoot) $craftsmanRoot
Add-Check "systemd-unit-template" (Test-Path $systemdUnit) $systemdUnit
Add-Check "systemd-env-template" (Test-Path $systemdEnv) $systemdEnv
Add-Check "nginx-template" (Test-Path $nginxConf) $nginxConf
Add-Check "workspace-dir" (Test-Path (Join-Path $craftsmanRoot "workspace")) (Join-Path $craftsmanRoot "workspace")
Add-Check "callbacks-dir" (Test-Path (Join-Path $craftsmanRoot "callbacks")) (Join-Path $craftsmanRoot "callbacks")

$checks | ConvertTo-Json -Depth 4
