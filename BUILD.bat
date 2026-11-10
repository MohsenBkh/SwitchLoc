@echo off
REM ==========================================================================
REM  BUILD.bat -- One-click SwitchLoc build -> SINGLE-FILE desktop exe
REM ==========================================================================
REM  1. Checks Python 3.10+ on PATH.
REM  2. Installs the dependencies directly into the Python found on PATH
REM     (no virtual environment).
REM  3. Import smoke test + GUI smoke test (offscreen Qt).
REM  4. Engineering test suite (skip with SKIP_TESTS=1).
REM  5. Builds dist\SwitchLoc.exe (one file, no console, icon, Qt splash).
REM  6. Copies projects\ + data\ + README.md next to the exe.
REM
REM  Optional: set WITH_GPKG=1 to also install GeoPackage support
REM  (geopandas/pyogrio -- large; not needed for Shapefile/GeoJSON/Excel).
REM
REM  Runtime errors are written to the rotating log
REM  %LOCALAPPDATA%\SwitchLoc\logs\switchloc.log (and shown in a message box).
REM ==========================================================================

setlocal EnableExtensions
cd /d "%~dp0"
title SwitchLoc Build (single-file exe)
chcp 65001 >nul 2>&1

echo ============================================================
echo   SwitchLoc -- One-Click Build  ^(single-file desktop exe^)
echo ============================================================
echo.

echo [1/6] Checking Python...
set "SYSPY=python"
"%SYSPY%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo and check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)
"%SYSPY%" --version
"%SYSPY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.10 or newer is required.
    pause
    exit /b 1
)

echo.
echo [2/6] Installing dependencies into the current Python ^(a few minutes^)...
set "PY=%SYSPY%"
"%PY%" -m pip install --disable-pip-version-check -r requirements-dev.txt -q
if errorlevel 1 goto :fail_deps
if "%WITH_GPKG%"=="1" (
    "%PY%" -m pip install --disable-pip-version-check -r requirements-gpkg.txt -q
    if errorlevel 1 goto :fail_deps
)
echo   Dependencies OK.

echo.
echo [3/6] Import + GUI smoke test...
set "PYTHONPATH=%~dp0src"
"%PY%" -c "import switchloc, switchloc.ui.qt.main_window; print('imports OK')"
if errorlevel 1 goto :fail_import
set "QT_QPA_PLATFORM=offscreen"
"%PY%" -m pytest tests\unit\test_ui_chrome.py -q --disable-warnings
if errorlevel 1 goto :fail_import
set "QT_QPA_PLATFORM="

echo.
echo [4/6] Engineering test suite...
if "%SKIP_TESTS%"=="1" goto :skip_tests
set "QT_QPA_PLATFORM=offscreen"
"%PY%" -m pytest tests -q --disable-warnings
if errorlevel 1 goto :fail_tests
set "QT_QPA_PLATFORM="
echo   All tests passed.
goto :tests_done
:skip_tests
echo   Skipped ^(SKIP_TESTS=1^).
:tests_done

echo.
echo [5/6] Building dist\SwitchLoc.exe ...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
set "EXTRA="
if "%WITH_GPKG%"=="1" set "EXTRA=--collect-submodules=geopandas --collect-submodules=pyogrio"
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name SwitchLoc --icon build_assets\icon.ico --add-data "build_assets\splash.png;build_assets" --add-data "build_assets\logo.png;build_assets" --add-data "build_assets\icon.png;build_assets" --add-data "build_assets\fonts;build_assets\fonts" --collect-all arabic_reshaper --collect-all bidi --paths src --hidden-import=shapefile --hidden-import=PySide6.QtSvg --hidden-import=matplotlib.backends.backend_qtagg --hidden-import=switchloc.ui.osm_tiles --hidden-import=switchloc.ui.qt.splash --hidden-import=switchloc.ui.qt.settings_dialog --hidden-import=switchloc.ui.qt.chrome --hidden-import=switchloc.ui.qt.theme --hidden-import=switchloc.ui.qt.icons --hidden-import=switchloc.ui.qt.i18n --hidden-import=switchloc.ui.qt.worker %EXTRA% --exclude-module IPython --exclude-module switchloc.cli build_tools\entry_gui.py
if errorlevel 1 goto :fail_build
if not exist "dist\SwitchLoc.exe" goto :fail_build

echo.
echo [6/6] Making dist\ self-contained...
if exist "projects" (
    xcopy /e /i /y "projects" "dist\projects\" >nul
    echo   Copied projects\ next to the exe.
)
if exist "data" (
    xcopy /e /i /y "data" "dist\data\" >nul
    echo   Copied data\ next to the exe.
)
if exist "README.md" copy /y "README.md" "dist\" >nul

echo.
echo ============================================================
echo   BUILD SUCCEEDED   -^>  dist\SwitchLoc.exe
echo   RUN.bat starts it; no Python needed on the target machine.
echo ============================================================
echo.
pause
endlocal
exit /b 0

:fail_deps
echo ERROR: failed to install dependencies.
goto :fail_end
:fail_import
echo ERROR: smoke test failed (see messages above).
goto :fail_end
:fail_tests
echo ERROR: unit tests failed -- build stopped. Fix the tests or run
echo       with SKIP_TESTS=1 to skip them.
goto :fail_end
:fail_build
echo.
echo ============================================================
echo   BUILD FAILED -- see the errors above.
echo ============================================================
:fail_end
echo.
pause
exit /b 1
