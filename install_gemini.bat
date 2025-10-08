@echo off
echo Installing Google Gemini API...
pip install google-generativeai>=0.3.0

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Installation failed!
    pause
    exit /b 1
)

echo.
echo SUCCESS: Gemini API installed successfully!
echo You can now use AI insights in Amanuensis V2
pause
