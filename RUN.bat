@echo off
REM ==========================================================================
REM  RUN.bat -- One-click SwitchLoc launcher (single-file EXE / dist mode)
REM ==========================================================================
REM  Usage:
REM    RUN.bat                        -> desktop app  dist\SwitchLoc.exe
REM    RUN.bat projects\x.sqlite      -> desktop app on a project
REM
REM  NOTE: there is NO CLI executable anymore (user request) -- BUILD.bat
REM       produces only the desktop app. The GUI covers the whole study
REM       workflow (import / topology / placement / exports).
REM
REM  This launcher does NOT use Python, pip or any virtual environment.
REM  It only starts the single-file executable that BUILD.bat created in
REM  dist\ (SwitchLoc.exe: no console window, splash screen with a
REM  loading bar).  If it is missing, run BUILD.bat once -- after that
REM  RUN.bat works on any Windows machine without Python installed.
REM
REM  The GUI exe has no console; unexpected errors are written to the log
REM  %LOCALAPPDATA%\SwitchLoc\logs\switchloc.log and shown in a message box.
REM ==========================================================================

setlocal EnableExtensions
cd /d "%~dp0"
title SwitchLoc
chcp 65001 >nul 2>&1

set "GUI_EXE=dist\SwitchLoc.exe"

if not exist "%GUI_EXE%" goto :need_build
echo Starting SwitchLoc desktop app...
echo ^(the splash screen with the loading bar shows while the app loads^)
echo.
"%GUI_EXE%" %*
set RC=%ERRORLEVEL%
echo.
echo   SwitchLoc desktop app exited with code %RC%
if %RC% NEQ 0 echo   Check %LOCALAPPDATA%\SwitchLoc\logs\switchloc.log for details.
echo.
pause
goto :eof

:need_build
echo.
echo ============================================================
echo   ERROR: the executable has not been built yet.
echo   Expected: %GUI_EXE%
echo.
echo   Fix: run BUILD.bat once. It creates the single-file exe
echo   in dist\ -- after that RUN.bat needs no Python and
echo   no installation on this machine.
echo ============================================================
echo.
pause
exit /b 1

endlocal
