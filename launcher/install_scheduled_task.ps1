# Install Personal Agent as Windows Scheduled Task
# Run at logon, auto-restart on failure, hidden window
# REQUIRES: Run as Administrator for task registration

param(
    [switch]$Uninstall
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$TaskName = "PersonalAgent"
$BatPath = Join-Path $ScriptDir "run_bot.bat"

if ($Uninstall) {
    Write-Host "Removing scheduled task: $TaskName" -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Task removed." -ForegroundColor Green
    exit 0
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "ERROR: Must run as Administrator to install scheduled task." -ForegroundColor Red
    Write-Host "Right-click PowerShell -> Run as Administrator, then:" -ForegroundColor Yellow
    Write-Host "  & '$($MyInvocation.MyCommand.Path)'" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $BatPath)) {
    Write-Host "ERROR: run_bot.bat not found at $BatPath" -ForegroundColor Red
    exit 1
}

$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""
$Trigger = New-ScheduledTaskTrigger -AtLogon
$Principal = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Personal Agent - Telegram bot with auto-update" `
    -Force

# Start task now
Start-ScheduledTask -TaskName $TaskName

Write-Host "Task '$TaskName' installed and started." -ForegroundColor Green
Write-Host "Bot runs at logon. Launcher auto-pulls git and restarts on crash." -ForegroundColor Cyan
Write-Host "Uninstall: Run as Admin: & '$PSCommandPath' -Uninstall" -ForegroundColor DarkGray
