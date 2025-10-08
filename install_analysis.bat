@echo off
echo ================================================================
echo Amanuensis V2 - Therapy Analysis Dependencies Installation
echo ================================================================
echo.

echo Installing Claude API and async processing dependencies...
echo.

echo Step 1: Installing Anthropic Claude API client...
pip install anthropic>=0.25.0
if errorlevel 1 (
    echo ERROR: Failed to install anthropic
    pause
    exit /b 1
)

echo Step 2: Installing async HTTP client...
pip install aiohttp>=3.8.0
if errorlevel 1 (
    echo ERROR: Failed to install aiohttp
    pause
    exit /b 1
)

echo Step 3: Installing throttling utilities...
pip install asyncio-throttle>=1.0.2
if errorlevel 1 (
    echo ERROR: Failed to install asyncio-throttle
    pause
    exit /b 1
)

echo.
echo ================================================================
echo Therapy Analysis Dependencies Installed Successfully!
echo ================================================================
echo.
echo Next steps:
echo 1. Get your Claude API key from console.anthropic.com
echo 2. Run test_therapy_analysis.py to set up configuration
echo 3. Enable therapy analysis in Amanuensis V2
echo 4. Configure analysis frequency (30s to 5min intervals)
echo.

echo Testing therapy analysis installation...
python test_therapy_analysis.py

if errorlevel 1 (
    echo.
    echo WARNING: Therapy analysis test failed
    echo Please check the error messages above
    echo You may need to configure your Claude API key
) else (
    echo.
    echo SUCCESS: Therapy analysis system is ready!
)

echo.
echo IMPORTANT: Remember to add your Claude API key to analysis_config.json
echo You can get an API key from: https://console.anthropic.com/
echo.
pause