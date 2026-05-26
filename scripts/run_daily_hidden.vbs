' Запускает run_daily_guarded.bat скрыто (без окна консоли)
' Используется как Startup-страховка от пропусков Task Scheduler
Set objShell = WScript.CreateObject("WScript.Shell")
strPath = WScript.ScriptFullName
strDir = Left(strPath, InStrRev(strPath, "\"))
objShell.Run Chr(34) & strDir & "run_daily_guarded.bat" & Chr(34), 0, True
