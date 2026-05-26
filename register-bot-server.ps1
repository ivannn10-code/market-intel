$ErrorActionPreference = "Stop"

$TaskName = "market-intel-bot-server"
$Scripts = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "scripts"
$VbsPath = Join-Path $Scripts "bot_server_hidden.vbs"

Write-Host "Регистрирую '$TaskName' (постоянный сервис, запуск при входе в Windows)..." -ForegroundColor Cyan

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "  Удалена предыдущая версия" -ForegroundColor Gray
} catch {}

# Action: запуск через wscript.exe + .vbs (скрытое окно)
$Action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$VbsPath`"" `
    -WorkingDirectory $Scripts

# Trigger: при входе в Windows + при включении компьютера
$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn

# Settings: автоперезапуск при сбое, нет лимита времени работы (это сервис)
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

# Principal: Interactive (не требует админа)
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $LogonTrigger -Settings $Settings -Principal $Principal -Force | Out-Null

Write-Host ""
Write-Host "Задача зарегистрирована:" -ForegroundColor Green
Write-Host "  - Запуск при входе в Windows (At log on)" -ForegroundColor Gray
Write-Host "  - Окно НЕ показывается (через wscript.exe)" -ForegroundColor Gray
Write-Host "  - Бесконечная работа (ExecutionTimeLimit=0)" -ForegroundColor Gray
Write-Host "  - Автоперезапуск x3 каждую минуту при сбое" -ForegroundColor Gray
Write-Host ""
Write-Host "Стартую прямо сейчас:" -ForegroundColor Yellow
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "  LastRunTime: $($info.LastRunTime)" -ForegroundColor Gray
Write-Host "  LastTaskResult: $($info.LastTaskResult)" -ForegroundColor Gray
Write-Host ""
Write-Host "Управление:" -ForegroundColor Yellow
Write-Host "  Остановить:  Stop-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  Перезапуск:  Stop-ScheduledTask -TaskName '$TaskName'; Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  Статус:      Get-ScheduledTaskInfo -TaskName '$TaskName'" -ForegroundColor Gray
