' Citrine desktop launcher — opens the app with no visible terminal window.
' Used by the desktop shortcut. Because there is no console to read, the dev
' output is redirected to a log file so a failed launch is still diagnosable
' rather than a silent nothing.
Option Explicit

Dim fso, sh, scriptDir, root, logDir, logFile
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scriptDir)

logDir = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Citrine"
If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)
logFile = logDir & "\launch.log"

sh.CurrentDirectory = root
' Window style 0 = hidden; False = do not wait for the app to exit.
sh.Run "cmd /c npm run dev > """ & logFile & """ 2>&1", 0, False
