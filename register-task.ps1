$ErrorActionPreference = "Stop"

$TaskName = "market-intel-daily"
$Scripts = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "scripts"
$VbsPath = Join-Path $Scripts "run_daily_hidden.vbs"

Write-Host "Регистрирую '$TaskName' через VBS-обёртку (скрытый запуск без админа)..." -ForegroundColor Cyan

# Удалить старую если есть
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "  Удалена предыдущая версия" -ForegroundColor Gray
} catch {}

# Запуск через wscript.exe + .vbs — окно консоли не появляется вообще
$Action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$VbsPath`"" `
    -WorkingDirectory $Scripts

# Триггер: ежедневно в 07:00
$Trigger = New-ScheduledTaskTrigger -Daily -At "07:00"

# Настройки: запуск при ближайшей возможности если пропустили, не глушить при батарее
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

# Принципал: Interactive (не требует админских прав)
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null

Write-Host ""
Write-Host "Задача зарегистрирована:" -ForegroundColor Green
Write-Host "  - Запуск каждый день в 07:00" -ForegroundColor Gray
Write-Host "  - Окно НЕ показывается (через wscript.exe + run_daily_hidden.vbs)" -ForegroundColor Gray
Write-Host "  - StartWhenAvailable — если комп выключен в 7:00, запустится при включении" -ForegroundColor Gray
Write-Host "  - Restart x2 каждые 10 мин при сбое" -ForegroundColor Gray
Write-Host ""
Write-Host "Запустить вручную для теста:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
