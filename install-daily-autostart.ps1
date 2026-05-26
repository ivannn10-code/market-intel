$Startup = [Environment]::GetFolderPath("Startup")
$ShortcutPath = "$Startup\market-intel-daily.lnk"
$VbsPath = "C:\Users\ivlan\OneDrive\Desktop\Вайбкодинг\.business\market-intel\scripts\run_daily_hidden.vbs"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "wscript.exe"
$Shortcut.Arguments = "`"$VbsPath`""
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Market Intel Daily Pipeline autostart guard"
$Shortcut.Save()

Write-Host "Shortcut created at: $ShortcutPath"
