@echo off
REM Build Pondside.exe with PyInstaller.
REM Run build_installer.bat afterwards to wrap it in a setup program.

cd /d "%~dp0"

echo ========================================
echo Pondside - Building Pondside.exe
echo ========================================
echo.

py -3.14 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller is not installed for Python 3.14.
    echo Install it with:  py -3.14 -m pip install pyinstaller
    pause
    exit /b 1
)

echo Building... this takes a minute or two.
echo.
py -3.14 -m PyInstaller --noconfirm --clean Pondside.spec
if errorlevel 1 (
    echo.
    echo ERROR: the build failed. See the output above.
    pause
    exit /b 1
)

if not exist "dist\Pondside.exe" (
    echo.
    echo ERROR: dist\Pondside.exe was not produced.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Built: dist\Pondside.exe
echo ========================================
echo.
echo To check the packaged build really found its art and its data:
echo     dist\Pondside.exe --selftest
echo then read dist\selftest.txt
echo.
pause
