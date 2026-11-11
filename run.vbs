Option Explicit

Dim fso, shell, appDir, mainPy, portablePythonw, portablePython, runBat, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Luon chay theo thu muc chua app, ke ca khi mo tu USB hoac shortcut.
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

mainPy = appDir & "\main.py"
portablePythonw = appDir & "\runtime\python\pythonw.exe"
portablePython = appDir & "\runtime\python\python.exe"
runBat = appDir & "\run.bat"

If Not fso.FileExists(mainPy) Then
    MsgBox "Khong tim thay main.py trong:" & vbCrLf & appDir & vbCrLf & vbCrLf & _
           "Hay copy lai day du toan bo thu muc app.", _
           vbCritical, "Android Scrcpy Manager"
    WScript.Quit 1
End If

If fso.FileExists(portablePythonw) Then
    cmd = Chr(34) & portablePythonw & Chr(34) & " " & Chr(34) & mainPy & Chr(34)
    shell.Run cmd, 1, False
    WScript.Quit 0
End If

If fso.FileExists(portablePython) Then
    cmd = Chr(34) & portablePython & Chr(34) & " " & Chr(34) & mainPy & Chr(34)
    shell.Run cmd, 1, False
    WScript.Quit 0
End If

If fso.FileExists(runBat) Then
    shell.Run Chr(34) & runBat & Chr(34), 1, False
    WScript.Quit 0
End If

MsgBox "Thieu runtime Python portable trong:" & vbCrLf & appDir & vbCrLf & vbCrLf & _
       "Hay copy lai day du toan bo thu muc app.", _
       vbCritical, "Android Scrcpy Manager"
WScript.Quit 1
