<#
.SYNOPSIS
  Install, inspect or remove the daily petmax.ro collection task (Windows Task Scheduler).

.DESCRIPTION
  DECISIONS.md ADR-0010: one scraper goes on a daily schedule before the other two adapters
  exist, because price history is wall-clock and a day not collected cannot be recovered.

  The task runs `scripts/scrape.py --source <name> --limit 0` once a day and appends both
  streams to `logs/scrape-<source>.log`.

  It is registered for the current user with -StartWhenAvailable, so a run missed because the
  machine was off or asleep is caught up at the next opportunity rather than skipped. It does
  NOT run while the user is logged off - making it do that needs a stored password or a service
  account, which is not worth it here: the Phase 7 VPS is where collection becomes continuous,
  and there it is a cron entry, not this task. Until then, a day the machine never wakes is a
  day of history lost, and `make status` will show it as a gap.

  Postgres must be up for the run to persist anything (`docker compose up -d db`). A run that
  cannot reach the database fails loudly in the log rather than silently collecting nothing.

.EXAMPLE
  .\scripts\schedule_daily.ps1 -Install
  .\scripts\schedule_daily.ps1 -Status
  .\scripts\schedule_daily.ps1 -RunNow
  .\scripts\schedule_daily.ps1 -Remove
#>
[CmdletBinding(DefaultParameterSetName = 'Status')]
param(
    [Parameter(ParameterSetName = 'Install')][switch]$Install,
    [Parameter(ParameterSetName = 'Remove')][switch]$Remove,
    [Parameter(ParameterSetName = 'Status')][switch]$Status,
    [Parameter(ParameterSetName = 'RunNow')][switch]$RunNow,
    [string]$Source = 'petmax_ro',
    # 06:10 local: after any overnight price changes have settled, well outside shop peak hours.
    [string]$At = '06:10'
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$TaskName = "PricePilot-scrape-$Source"
$LogDir = Join-Path $Root 'logs'
$LogFile = Join-Path $LogDir "scrape-$Source.log"

function Get-UvPath {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $uv) {
        throw "uv is not on PATH. The scheduled task needs its absolute path - install uv or run from a shell where it resolves."
    }
    return $uv.Source
}

if ($Install) {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    $uvPath = Get-UvPath

    # cmd.exe wraps the call only so both stdout and stderr can be appended to one log.
    $inner = "`"$uvPath`" run python scripts/scrape.py --source $Source --limit 0"
    $argument = "/c cd /d `"$Root`" && echo [%DATE% %TIME%] start >> `"$LogFile`" && $inner >> `"$LogFile`" 2>&1 && echo [%DATE% %TIME%] done >> `"$LogFile`""

    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $argument
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 3)

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "PricePilot daily collection from $Source (Phase 1)." `
        -Force | Out-Null

    Write-Host "Installed '$TaskName' - daily at $At."
    Write-Host "Log:  $LogFile"
    Write-Host "Check with: .\scripts\schedule_daily.ps1 -Status"
    exit 0
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'. Collection has STOPPED - history stops accumulating now."
    exit 0
}

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Triggered '$TaskName'. Follow it with: Get-Content '$LogFile' -Wait -Tail 20"
    exit 0
}

# -- Status (default) --------------------------------------------------------
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "NOT INSTALLED: '$TaskName'"
    Write-Host "Install it with: .\scripts\schedule_daily.ps1 -Install"
    exit 1
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "task           $TaskName"
Write-Host "state          $($task.State)"
Write-Host "next run       $($info.NextRunTime)"
Write-Host "last run       $($info.LastRunTime)"
Write-Host "last result    $($info.LastTaskResult)  (0 = ok, 1 = volume alert or failure, 2/3 = refused to run)"
if (Test-Path $LogFile) {
    Write-Host "`n-- last 15 log lines ------------------------------------------------"
    Get-Content $LogFile -Tail 15
} else {
    Write-Host "`nNo log yet at $LogFile - the task has not run."
}
