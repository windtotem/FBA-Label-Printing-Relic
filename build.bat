@echo off
title FBA Label Printing Relic
color 0A

echo ============================================
echo   FBA Label Printing Relic — Build Script
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

:: Install / upgrade dependencies
echo [1/3] Installing dependencies...
pip install --upgrade pypdf pymupdf pillow pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/3] Building executable...
pyinstaller --onefile --windowed --name "FBA Label Printing Relic" pdf_processor.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Cleaning up build artifacts...
rmdir /s /q build
del /q FBA Label Printing Relic.spec

echo.
echo ============================================
echo   Build complete!
echo   Your executable is in the dist\ folder:
echo   dist\FBA Label Printing Relic.exe
echo ============================================
echo.
pause
