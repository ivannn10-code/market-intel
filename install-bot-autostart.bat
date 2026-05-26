@echo off
chcp 65001 >/dev/null
title Установка автозапуска бота

echo.
echo =============================================
echo  Установка автозапуска market-intel-bot-server
echo =============================================
echo.
echo Регистрирует Windows Task Scheduler, который
echo автоматически запустит бота при следующем
echo входе в Windows.
echo.
echo Окно бота никогда не появляется (скрытый запуск).
echo.
pause

schtasks /Delete /TN "market-intel-bot-server" /F >/dev/null 2>&1

set VBS="%~dp0scripts\bot_server_hidden.vbs"
schtasks /Create /TN "market-intel-bot-server" /SC ONLOGON /TR "wscript.exe %VBS%" /RL LIMITED /F

if errorlevel 1 (
    echo.
    echo [!] Ошибка регистрации. Попробуй запустить этот .bat от имени администратора:
    echo     Правый клик по install-bot-autostart.bat → Запуск от имени администратора
    pause
    exit /b 1
)

echo.
echo Запускаю бота прямо сейчас (без перезагрузки)...
schtasks /Run /TN "market-intel-bot-server"

echo.
echo =============================================
echo  Готово!
echo =============================================
echo.
echo Бот автоматически стартует при каждом входе
echo в Windows. Окно консоли не появляется.
echo.
echo Проверка статуса:
echo   schtasks /Query /TN market-intel-bot-server
echo.
echo Остановить:
echo   schtasks /End /TN market-intel-bot-server
echo.
pause
