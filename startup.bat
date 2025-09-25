@echo off
echo ========================================
echo    AMANUENSIS - Enhanced Transcription System
echo    Real-time Local Speech-to-Text
echo ========================================
echo.

cd /d "%~dp0"

echo Checking system requirements...
python test_fixes.py
if %errorlevel% neq 0 (
    echo.
    echo System check failed! Please review the errors above.
    echo.
    pause
    exit /b 1
)

echo.
echo System check passed! Starting Amanuensis...
echo.

python run_enhanced_amanuensis.py

echo.
echo Application has closed.
pause