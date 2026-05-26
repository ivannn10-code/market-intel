@echo off
REM Guarded запуск run_daily: проверяет, был ли успешный запуск сегодня.
REM Если был — exit 0. Если не было — запускает run_daily.bat.
REM Используется как страховка через Startup folder.

setlocal
cd /d "%~dp0"

set GUARD_FILE=..\logs\last-success-date.txt
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set TODAY=%%I

if exist "%GUARD_FILE%" (
    set /p LAST=<"%GUARD_FILE%"
    if "%LAST%"=="%TODAY%" (
        REM Сегодня уже отработал — выходим
        exit /b 0
    )
)

REM Запускаем основной цикл
call run_daily.bat

REM Записываем дату успешного завершения
echo %TODAY%>"%GUARD_FILE%"

endlocal
