' Запускает bot_server.py через venv-Python скрыто (без окна консоли)
Set objShell = WScript.CreateObject("WScript.Shell")
strPath = WScript.ScriptFullName
strDir = Left(strPath, InStrRev(strPath, "\"))
' venv Python в ..\venv\Scripts\python.exe относительно scripts/
strPython = strDir & "..\venv\Scripts\python.exe"
strScript = strDir & "bot_server.py"
' 0 = hidden window, True = wait for completion
' set environment so Python uses UTF-8 for print
objShell.Run "cmd /c set PYTHONIOENCODING=utf-8 && """ & strPython & """ -u """ & strScript & """", 0, True
