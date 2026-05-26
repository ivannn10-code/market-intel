$Startup = [Environment]::GetFolderPath("Startup")
$ShortcutPath = "$Startup\market-intel-bot.lnk"
$VbsPath = "C:\Users\ivlan\OneDrive\Desktop\Вайбкодинг\.business\market-intel\scripts\bot_server_hidden.vbs"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "wscript.exe"
$Shortcut.Arguments = "`"$VbsPath`""
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Market Intel Bot autostart"
$Shortcut.Save()

Write-Host "Shortcut created at: $ShortcutPath"
Get-Item $ShortcutPath | Format-List Name, FullName, LastWriteTime
