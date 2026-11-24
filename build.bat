@echo off
rem Builds Recoil as a Windows program: Builds\Recoil\Recoil.exe in this folder.
rem Close Unity first (it cannot build a project that is open in another Unity), then double-click this file.
rem It takes a few minutes the first time. Inside Unity the same is Recoil > Build > Windows Game (.exe).
setlocal
cd /d "%~dp0"

set "UNITY=%UNITY_EXE%"
if defined UNITY if exist "%UNITY%" goto found
set "UNITY=C:\Program Files\Unity\Hub\Editor\6000.3.29f1\Editor\Unity.exe"
if exist "%UNITY%" goto found
for /d %%D in ("C:\Program Files\Unity\Hub\Editor\6000.3.*") do if exist "%%D\Editor\Unity.exe" set "UNITY=%%D\Editor\Unity.exe"
if exist "%UNITY%" goto found
echo Could not find Unity 6000.3 in C:\Program Files\Unity\Hub\Editor.
echo If it is somewhere else, run this first, with your Unity.exe's real path:
echo     set UNITY_EXE=D:\Unity\6000.3.29f1\Editor\Unity.exe
echo and then run build.bat from the same window.
echo.
pause
exit /b 1

:found
echo Building Recoil.exe with:
echo     %UNITY%
echo This takes a few minutes. Nothing shows until it is done; the details go to build.log.
echo.
"%UNITY%" -batchmode -quit -projectPath "%~dp0game" -executeMethod Recoil.EditorTools.BuildGame.BuildWindowsFromCommandLine -logFile "%~dp0build.log"
if errorlevel 1 goto failed
if not exist "Builds\Recoil\Recoil.exe" goto failed

echo Done: Builds\Recoil\Recoil.exe
echo Double-click it to play. To give the game to someone, copy the whole Builds\Recoil folder.
echo.
start "" explorer "%~dp0Builds\Recoil"
pause
exit /b 0

:failed
echo.
echo The build did not finish. Why, from build.log:
echo.
findstr /c:"RECOIL BUILD FAILED" /c:"error CS" /c:"another Unity instance" /c:"No valid Unity Editor license" "%~dp0build.log"
echo.
echo If it says another Unity instance is running, close Unity and try again.
echo Otherwise send build.log (in this folder).
echo.
pause
exit /b 1
