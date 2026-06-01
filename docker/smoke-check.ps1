$ErrorActionPreference = "Stop"

$BaseUrl = if ($args.Length -gt 0) { $args[0] } else { "http://127.0.0.1:8791" }

Write-Output "== health =="
Invoke-RestMethod "$BaseUrl/health" | ConvertTo-Json -Depth 8

Write-Output "== readyz =="
Invoke-RestMethod "$BaseUrl/readyz" | ConvertTo-Json -Depth 8

Write-Output "== dashboard =="
(Invoke-WebRequest -UseBasicParsing "$BaseUrl/dashboard").StatusCode

Write-Output "== dashboard overview =="
Invoke-RestMethod "$BaseUrl/dashboard/api/overview" | ConvertTo-Json -Depth 8
