@echo off
REM ============================================================
REM  Исторический бэкфил постов из Telegram
REM  Запуск:
REM    .\scripts\run_backfill.bat 15
REM  Аргумент — число дней назад (по умолчанию 15)
REM ============================================================

setlocal
cd /d "%~dp0"

set DAYS=%1
if "%DAYS%"=="" set DAYS=15

if exist "..\venv\Scripts\activate.bat" call "..\venv\Scripts\activate.bat"

echo.
echo === Парсинг истории за %DAYS% дней (с паузой 4 сек между каналами) ===
python parser.py --days %DAYS% --sleep 4 --limit 5000
if errorlevel 1 (
    echo === PARSER FAILED ===
    exit /b 1
)

echo.
echo === AI-обработка через Claude ===
python processor.py

endlocal
