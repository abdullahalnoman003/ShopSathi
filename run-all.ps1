<#
  ShopSathi: start everything for a local test with ONE command.

  Usage (PowerShell, from E:\ShopSathi):
      .\run-all.ps1                 # database + redis, migrations, seed, API, worker, frontend
      .\run-all.ps1 -Ngrok          # also starts ngrok on port 8000 (for Facebook)
      .\run-all.ps1 -Beat           # also starts the weekly-summary scheduler
      .\run-all.ps1 -NoSeed         # skip the demo data
      .\run-all.ps1 -NoBrowser      # do not open the browser

  Stop everything with:  .\stop-all.ps1
  The AI engine is not a separate server: it is installed into the backend.
#>
param(
    [switch]$Ngrok,
    [switch]$Beat,
    [switch]$NoSeed,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"   # native tools (docker) write progress to stderr; exit codes are checked explicitly
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$database = Join-Path $root "database"
$py = Join-Path $backend ".venv\Scripts\python.exe"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- checks
Step "Checking requirements"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker is not installed or not in PATH." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker is not running. Start Docker Desktop and run this script again." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js (npm) is not installed." }
if (-not (Test-Path $py)) {
    Fail "Backend virtual environment not found. Create it once:`n  cd backend`n  py -3.12 -m venv .venv`n  .\.venv\Scripts\Activate.ps1`n  pip install -r requirements.txt"
}
& $py -c "import pydantic_core, fastapi, celery" 2>$null
if ($LASTEXITCODE -ne 0) { Fail "The backend packages are broken or missing. In backend run:  .\.venv\Scripts\python.exe -m pip install -r requirements.txt" }
if (-not (Test-Path (Join-Path $backend ".env"))) { Fail "backend\.env is missing. Copy backend\.env.example to backend\.env and fill it in (JWT_SECRET, FB_*, OPENAI_API_KEY)." }
if (-not (Test-Path (Join-Path $database ".env"))) { Copy-Item (Join-Path $database ".env.example") (Join-Path $database ".env"); Write-Host "Created database\.env from the example." }
if (-not (Test-Path (Join-Path $frontend ".env.local"))) { Copy-Item (Join-Path $frontend ".env.example") (Join-Path $frontend ".env.local"); Write-Host "Created frontend\.env.local from the example." }

# ---------------------------------------------------------------- database + redis
Step "Starting PostgreSQL and Redis (Docker)"
Push-Location $database
docker compose up -d
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "docker compose failed." }
Pop-Location

Step "Waiting for PostgreSQL and Redis to be healthy"
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    $pg = docker inspect --format "{{.State.Health.Status}}" shopsathi-postgres 2>$null
    $rd = docker inspect --format "{{.State.Health.Status}}" shopsathi-redis 2>$null
    if ($pg -eq "healthy" -and $rd -eq "healthy") { $ok = $true; break }
    Start-Sleep -Seconds 3
}
if (-not $ok) { Fail "PostgreSQL or Redis did not become healthy. Run: docker compose -f database\docker-compose.yml logs" }

# the ports in database\.env (Docker) and backend\.env (the app) must agree
$dbEnv = Get-Content (Join-Path $database ".env")
$beEnv = Get-Content (Join-Path $backend ".env")
$pgPort = ($dbEnv | Where-Object { $_ -match "^POSTGRES_PORT=" }) -replace "^POSTGRES_PORT=", ""
$rdPort = ($dbEnv | Where-Object { $_ -match "^REDIS_PORT=" }) -replace "^REDIS_PORT=", ""
$dbUrl = ($beEnv | Where-Object { $_ -match "^DATABASE_URL=" }) -join ""
$rdUrl = ($beEnv | Where-Object { $_ -match "^REDIS_URL=" }) -join ""
# fix the ports in backend\.env automatically (only the port numbers change, nothing else in the file)
$envPath = Join-Path $backend ".env"
$envText = Get-Content $envPath -Raw
$fixed = $false
if ($pgPort -and $dbUrl -notmatch "@[^/:]+:$pgPort/") {
    $envText = [regex]::Replace($envText, "(?m)^((?:TEST_)?DATABASE_URL=\S*?@[^/:\s]+):\d+/", "`${1}:$pgPort/")
    $fixed = $true
}
if ($rdPort -and $rdUrl -notmatch ":$rdPort(/|$)") {
    $envText = [regex]::Replace($envText, "(?m)^(REDIS_URL=redis://[^/:\s]+):\d+", "`${1}:$rdPort")
    $fixed = $true
}
if ($fixed) {
    [System.IO.File]::WriteAllText($envPath, $envText, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Fixed the database/Redis ports in backend\.env to match Docker (PostgreSQL $pgPort, Redis $rdPort)." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- migrations + seed
Step "Running database migrations"
Push-Location $backend
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Migrations failed." }
if (-not $NoSeed) {
    Step "Loading demo data (safe to repeat)"
    & $py -m app.cli seed
    Step "Preparing the one-click demo logins (local only)"
    & $py -m app.cli demo-accounts
}
Pop-Location

# ---------------------------------------------------------------- frontend packages
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Step "Installing frontend packages (first run only, a few minutes)"
    Push-Location $frontend
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "npm install failed." }
    Pop-Location
}

# ---------------------------------------------------------------- start the services, one window each
function Start-Window($title, $workdir, $command) {
    $full = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$workdir'; $command"
    Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $full | Out-Null
    Write-Host "Started: $title"
}

Step "Starting the services"
Start-Window "ShopSathi API (8000)" $backend "& '$py' -m uvicorn app.main:app --reload --port 8000"
Start-Sleep -Seconds 3
Start-Window "ShopSathi Worker" $backend "& '$py' -m celery -A app.workers.celery_app worker --loglevel=info --pool=solo"
if ($Beat) { Start-Window "ShopSathi Beat" $backend "& '$py' -m celery -A app.workers.celery_app beat --loglevel=info" }
Start-Window "ShopSathi Frontend (3000)" $frontend "npm run dev"
if ($Ngrok) {
    if (Get-Command ngrok -ErrorAction SilentlyContinue) { Start-Window "ngrok (8000)" $root "ngrok http 8000" }
    else { Write-Host "ngrok was not found in PATH: skipped." -ForegroundColor Yellow }
}

# ---------------------------------------------------------------- wait for the API and the frontend
Step "Waiting for the API and the frontend"
$apiOk = $false
for ($i = 0; $i -lt 40; $i++) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 3; if ($r.StatusCode -eq 200) { $apiOk = $true; break } } catch {}
    Start-Sleep -Seconds 3
}
if ($apiOk) { Write-Host "API is up:      http://localhost:8000/api/v1/health" -ForegroundColor Green } else { Write-Host "API did not answer yet: look at the 'ShopSathi API' window." -ForegroundColor Yellow }
$feOk = $false
for ($i = 0; $i -lt 40; $i++) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:3000" -TimeoutSec 3; $feOk = $true; break } catch {}
    Start-Sleep -Seconds 3
}
if ($feOk) { Write-Host "Frontend is up: http://localhost:3000" -ForegroundColor Green } else { Write-Host "Frontend did not answer yet: look at the 'ShopSathi Frontend' window." -ForegroundColor Yellow }

if (-not $NoBrowser -and $feOk) { Start-Process "http://localhost:3000" }

Write-Host "`nAll started. Demo owner (from seed): see database/README.md and docs/USER_GUIDE.md." -ForegroundColor Green
Write-Host "To stop everything run:  .\stop-all.ps1"

