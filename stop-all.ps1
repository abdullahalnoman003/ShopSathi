<#
  Stops everything started by run-all.ps1.
      .\stop-all.ps1            # stops API, worker, beat, frontend, ngrok and the Docker containers
      .\stop-all.ps1 -KeepDocker  # leave PostgreSQL and Redis running
#>
param([switch]$KeepDocker)

$root = $PSScriptRoot

Write-Host "Stopping the ShopSathi windows and processes ..." -ForegroundColor Cyan
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        ($_.CommandLine -match "ShopSathi (API|Worker|Beat|Frontend)") -or
        ($_.CommandLine -match "app\.workers\.celery_app") -or
        ($_.CommandLine -match "uvicorn app\.main:app") -or
        ($_.CommandLine -match "ngrok http 8000")
    ) -and $_.ProcessId -ne $PID
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# uvicorn --reload leaves child processes behind when its parent window is closed: they keep the port busy.
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "multiprocessing\.spawn" -and $_.CommandLine -match "parent_pid=(\d+)" } | ForEach-Object {
    $parentPid = [int]$Matches[1]
    if (-not (Get-Process -Id $parentPid -ErrorAction SilentlyContinue)) { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

if (-not $KeepDocker) {
    Write-Host "Stopping PostgreSQL and Redis ..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "database")
    docker compose down
    Pop-Location
}
Write-Host "Done." -ForegroundColor Green
