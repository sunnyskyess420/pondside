@echo off
REM Wrap dist\Pondside.exe into a per-user setup program with Inno Setup 7.
REM Run build_pondside_exe.bat first.

cd /d "%~dp0"

echo ========================================
echo Pondside - Building the installer
echo ========================================
echo.

if not exist "dist\Pondside.exe" (
    echo ERROR: dist\Pondside.exe not found.
    echo Run build_pondside_exe.bat first.
    pause
    exit /b 1
)

set "INNO_PATH=C:\Program Files\Inno Setup 7\ISCC.exe"
if exist "%INNO_PATH%" goto :found_inno
set "INNO_PATH=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if exist "%INNO_PATH%" goto :found_inno
where iscc >nul 2>&1
if not errorlevel 1 (
    set "INNO_PATH=iscc"
    goto :found_inno
)
echo ERROR: Inno Setup 7 compiler (ISCC.exe) not found.
echo Install it from https://jrsoftware.org/isdl.php
pause
exit /b 1

:found_inno

echo Using: %INNO_PATH%
echo.

"%INNO_PATH%" pondside.iss
if errorlevel 1 (
    echo.
    echo ERROR: the installer build failed. See the output above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Installer created
echo ========================================
echo.
dir /b installer_output\*.exe
echo.
pause
