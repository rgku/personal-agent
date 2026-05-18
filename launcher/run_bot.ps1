# Personal Agent Launcher
# Auto-update + auto-restart loop + PID lock (prevents duplicate launchers)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$RestartCode = 42
$CrashWait = 5
$LauncherLock = Join-Path $ProjectDir "data\launcher.pid"

Set-Location $ProjectDir

# === LAUNCHER PID LOCK ===
# Kill ALL bot processes first (cleanup stale doubles)
$BotProcs = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'run\.py' }
if ($BotProcs) {
    Write-Host "  Cleaning old bot instances..." -ForegroundColor DarkYellow
    $BotProcs | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# Remove stale PID files (bot + launcher)
$BotPidFile = Join-Path $ProjectDir "data\bot.pid"
if (Test-Path $BotPidFile) { Remove-Item $BotPidFile -Force }
if (Test-Path $LauncherLock) { Remove-Item $LauncherLock -Force }

# Now claim launcher lock
$MyPid = [System.Diagnostics.Process]::GetCurrentProcess().Id
Set-Content -Path $LauncherLock -Value "$MyPid" -NoNewline
Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Launcher PID lock acquired: $MyPid" -ForegroundColor Cyan

try {
    while ($true) {
        Write-Host "=== Personal Agent Launcher ===" -ForegroundColor Cyan
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Checking for updates..." -ForegroundColor Yellow

        # Verify we still own the lock (in case another launcher replaced it)
        if (Test-Path $LauncherLock) {
            $LockedPid = Get-Content $LauncherLock -Raw | ForEach-Object { $_.Trim() }
            if ($LockedPid -ne "$MyPid") {
                Write-Host "FATAL: Another launcher (PID $LockedPid) took over. Exiting." -ForegroundColor Red
                exit 1
            }
        }

        # Git pull
        if (Test-Path ".git") {
            git pull 2>&1 | ForEach-Object { Write-Host "  git: $_" }
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  WARN: git pull failed, continuing" -ForegroundColor DarkYellow
            }
        } else {
            Write-Host "  SKIP: not a git repo" -ForegroundColor DarkYellow
        }

        # Pip install
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Installing dependencies..." -ForegroundColor Yellow
        pip install -r requirements.txt --quiet 2>&1 | ForEach-Object { }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  WARN: pip install had issues" -ForegroundColor DarkYellow
        }

        # Clean stale bot.pid
        if (Test-Path $BotPidFile) { Remove-Item $BotPidFile -Force }

        # Run bot
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting bot..." -ForegroundColor Green
        python run.py
        $ExitCode = $LASTEXITCODE

        if ($ExitCode -eq $RestartCode) {
            Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Bot update restart. Reloading in 3s..." -ForegroundColor Cyan
            Start-Sleep -Seconds 3
            continue
        }

        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Bot stopped (code=$ExitCode). Restarting in ${CrashWait}s..." -ForegroundColor Red
        Start-Sleep -Seconds $CrashWait
    }
} finally {
    # Release launcher lock on exit
    if (Test-Path $LauncherLock) {
        $LockedPid = Get-Content $LauncherLock -Raw | ForEach-Object { $_.Trim() }
        if ($LockedPid -eq "$MyPid") {
            Remove-Item $LauncherLock -Force
            Write-Host "Launcher PID lock released" -ForegroundColor DarkYellow
        }
    }
}
