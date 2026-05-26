# ============================================================
#  setup.ps1 — автоматическая установка market-intel
#  Запуск: правый клик по файлу → Run with PowerShell
#  Или в терминале: powershell -ExecutionPolicy Bypass -File .\setup.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step($n, $text) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "  Шаг $n. $text" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
}

function Read-Pause($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Yellow
    Read-Host "Нажми Enter когда готов"
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Scripts = Join-Path $Root "scripts"
$Venv = Join-Path $Root "venv"
$EnvFile = Join-Path $Scripts ".env"
$EnvExample = Join-Path $Scripts "dotenv.example"

Write-Host @"

  __  __            _        _   ___       _       _
 |  \/  | __ _ _ __| | _____| |_|_ _|_ __ | |_ ___| |
 | |\/| |/ _\` | '__| |/ / _ \ __|| || '_ \| __/ _ \ |
 | |  | | (_| | |  |   <  __/ |_ | || | | | ||  __/ |
 |_|  |_|\__,_|_|  |_|\_\___|\__|___|_| |_|\__\___|_|

  Автоустановка парсера Telegram-каналов для Ивана
"@ -ForegroundColor Green

Write-Step 1 "Проверка Python"

$pythonOk = $false
try {
    $ver = & python --version 2>&1
    if ($ver -match "Python 3\.(1[1-9]|[2-9]\d)") {
        Write-Host "  ✓ Python уже установлен: $ver" -ForegroundColor Green
        $pythonOk = $true
    }
} catch {}

if (-not $pythonOk) {
    Write-Host "  Python не найден или слишком старый. Ставлю через winget..." -ForegroundColor Yellow
    try {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        # Перечитать PATH в текущей сессии
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $ver = & python --version 2>&1
        Write-Host "  ✓ Установлен: $ver" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ winget не справился. Открой https://www.python.org/downloads/windows/ и поставь Python 3.12 вручную (с галочкой Add to PATH), потом запусти setup.ps1 заново." -ForegroundColor Red
        Start-Process "https://www.python.org/downloads/windows/"
        exit 1
    }
}

Write-Step 2 "Создание виртуального окружения"

if (-not (Test-Path $Venv)) {
    & python -m venv $Venv
    Write-Host "  ✓ Создан venv: $Venv" -ForegroundColor Green
} else {
    Write-Host "  ✓ venv уже существует" -ForegroundColor Green
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvPip = Join-Path $Venv "Scripts\pip.exe"

Write-Step 3 "Установка зависимостей (Telethon, Anthropic, ...)"

& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPip install -r (Join-Path $Scripts "requirements.txt") --quiet
Write-Host "  ✓ Зависимости установлены" -ForegroundColor Green

Write-Step 4 "Получение API-ключей"

if (Test-Path $EnvFile) {
    Write-Host "  ✓ .env уже существует. Использую его (если хочешь пересоздать — удали и запусти setup.ps1 заново)." -ForegroundColor Green
} else {
    Copy-Item $EnvExample $EnvFile

    Write-Host @"

  Сейчас откроется 2 вкладки в браузере. Нужно получить 3 значения:

  ВКЛАДКА 1: my.telegram.org
    1. Войди по номеру телефона (получишь код в Telegram)
    2. Открой 'API development tools'
    3. Создай приложение (название любое, типа 'market-intel')
    4. Скопируй api_id (число) и api_hash (строку)

  ВКЛАДКА 2: console.anthropic.com
    1. Зарегистрируйся или войди
    2. Пополни баланс минимум на 5 долларов (Settings → Billing)
    3. API Keys → Create Key → скопируй (показывается один раз!)
"@ -ForegroundColor Yellow

    Read-Pause "Готов открыть вкладки?"
    Start-Process "https://my.telegram.org/auth"
    Start-Process "https://console.anthropic.com/settings/keys"

    Write-Host ""
    Write-Host "  Сейчас откроется блокнот с файлом .env — заполни 4 значения и сохрани (Ctrl+S)." -ForegroundColor Yellow
    Read-Pause "Готов открыть блокнот?"
    Start-Process notepad.exe $EnvFile -Wait

    Write-Host "  ✓ .env сохранён" -ForegroundColor Green
}

Write-Step 5 "Первичная авторизация в Telegram (придёт код)"

Write-Host @"

  Сейчас запустится init.py. Он попросит:
  1. Код подтверждения (придёт в Telegram от @Telegram)
  2. Если у тебя двухфакторка — облачный пароль

  Потом он автоматически импортирует обе твои addlist-папки и
  соберёт список всех каналов в sources.yaml + базу.
"@ -ForegroundColor Yellow

Read-Pause "Готов?"

Push-Location $Scripts
& $VenvPython init.py
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ init.py упал. Посмотри ошибку выше и запусти setup.ps1 заново." -ForegroundColor Red
    exit 1
}

Write-Step 6 "Первый сбор постов и AI-обработка"

Write-Host "  Запускаю parser.py (заберёт посты за последние 26ч)..." -ForegroundColor Yellow
Push-Location $Scripts
& $VenvPython parser.py
Write-Host ""
Write-Host "  Запускаю processor.py (AI-обработка через Claude)..." -ForegroundColor Yellow
& $VenvPython processor.py
Pop-Location

Write-Step 7 "Регистрация Task Scheduler (ежедневный запуск в 07:00)"

$TaskName = "market-intel-daily"
$BatPath = Join-Path $Scripts "run_daily.bat"

# Удаляем старую задачу если есть
schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

$Action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $Scripts
$Trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null

Write-Host "  ✓ Задача '$TaskName' зарегистрирована — будет запускаться каждый день в 07:00" -ForegroundColor Green

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  ✓ ВСЁ ГОТОВО" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Что дальше:"
Write-Host "  • База уже наполнена постами за последние сутки"
Write-Host "  • Дайджест за сегодня: $Root\digest\daily\"
Write-Host "  • Тематические файлы: $Root\digest\topics\"
Write-Host "  • Завтра в 07:00 — следующий автозапуск"
Write-Host ""
Write-Host "  Чтобы проверить статус:"
Write-Host "    cd $Scripts" -ForegroundColor Gray
Write-Host "    ..\venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "    python query.py --stats" -ForegroundColor Gray
Write-Host ""
