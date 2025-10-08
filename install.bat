@echo off
echo Installing Amanuensis V2 dependencies...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10 or higher from https://python.org
    pause
    exit /b 1
)

echo Python found. Installing dependencies...
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies
    echo You may need to run this as administrator or check your internet connection
    pause
    exit /b 1
)

echo.
echo Installation complete!
echo.
echo To run the application:
echo   python main.py
echo.
pause
