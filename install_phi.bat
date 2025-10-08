@echo off
echo ================================================================
echo Amanuensis V2 - PHI Detection Dependencies Installation
echo ================================================================
echo.

echo Installing Microsoft Presidio and spaCy for PHI detection...
echo.

echo Step 1: Installing Presidio Analyzer...
pip install presidio-analyzer>=2.2.33
if errorlevel 1 (
    echo ERROR: Failed to install presidio-analyzer
    pause
    exit /b 1
)

echo Step 2: Installing Presidio Anonymizer...
pip install presidio-anonymizer>=2.2.33
if errorlevel 1 (
    echo ERROR: Failed to install presidio-anonymizer
    pause
    exit /b 1
)

echo Step 3: Installing spaCy...
pip install spacy>=3.4.0
if errorlevel 1 (
    echo ERROR: Failed to install spacy
    pause
    exit /b 1
)

echo Step 4: Downloading spaCy English model...
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo ERROR: Failed to download spaCy English model
    echo This might be due to network issues. You can try again later with:
    echo python -m spacy download en_core_web_sm
    pause
    exit /b 1
)

echo.
echo ================================================================
echo PHI Detection Dependencies Installed Successfully!
echo ================================================================
echo.
echo You can now:
echo 1. Enable PHI detection in Amanuensis V2
echo 2. Run test_phi_detection.py to verify functionality
echo 3. Use the manual review interface during transcription
echo.

echo Testing PHI detection installation...
python test_phi_detection.py

if errorlevel 1 (
    echo.
    echo WARNING: PHI detection test failed
    echo Please check the error messages above
) else (
    echo.
    echo SUCCESS: PHI detection is working correctly!
)

echo.
pause