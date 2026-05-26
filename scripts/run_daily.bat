@echo off
REM ============================================================
REM  Ежедневный конвейер: парсинг → AI-обработка → алерты → дайджест
REM  По понедельникам дополнительно — weekly_digest в 7:30
REM  Запускается через Windows Task Scheduler в 07:00
REM ============================================================

setlocal
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8

if exist "..\venv\Scripts\activate.bat" call "..\venv\Scripts\activate.bat"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set DT=%%I
set LOGFILE=..\logs\daily-%DT%.log

REM Получаем день недели: 1=Monday ... 7=Sunday
for /f %%D in ('powershell -NoProfile -Command "[int](Get-Date).DayOfWeek"') do set DOW=%%D

echo === %date% %time% START (DayOfWeek=%DOW%) === >> "%LOGFILE%"

echo === [1/4] parser === >> "%LOGFILE%"
python -u parser.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo === PARSER FAILED, continuing === >> "%LOGFILE%"

echo === [2/4] processor === >> "%LOGFILE%"
python -u processor.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo === PROCESSOR FAILED, continuing === >> "%LOGFILE%"

echo === [3/4] alerts === >> "%LOGFILE%"
python -u notifier.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo === NOTIFIER FAILED, continuing === >> "%LOGFILE%"

echo === [4/4] daily digest === >> "%LOGFILE%"
python -u daily_digest.py >> "%LOGFILE%" 2>&1
if errorlevel 1 echo === DIGEST FAILED === >> "%LOGFILE%"

REM По понедельникам (DOW=1) — дополнительно недельная сводка
if "%DOW%"=="1" (
    echo === [5/5] WEEKLY DIGEST (Monday) === >> "%LOGFILE%"
    python -u weekly_digest.py --send >> "%LOGFILE%" 2>&1
)

echo === %date% %time% END === >> "%LOGFILE%"

endlocal
