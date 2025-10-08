@echo off
echo ==========================================
echo Amanuensis V2 - Advanced Diarization Setup
echo ==========================================
echo.

echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo ==========================================
echo PYANNOTE.AUDIO SETUP INSTRUCTIONS
echo ==========================================
echo.
echo The advanced speaker diarization feature requires pyannote.audio models.
echo These models require a HuggingFace account and token for download.
echo.
echo SETUP STEPS:
echo 1. Create account at https://huggingface.co/
echo 2. Visit https://huggingface.co/pyannote/speaker-diarization-3.1
echo 3. Accept the license agreement
echo 4. Generate access token at https://huggingface.co/settings/tokens
echo 5. Run: huggingface-cli login
echo    (Enter your token when prompted)
echo.
echo ALTERNATIVE: For testing without HF token:
echo - The app will attempt to load models automatically
echo - If it fails, advanced diarization will be disabled
echo - You can still use standard dual-channel diarization
echo.

echo ==========================================
echo GPU MEMORY REQUIREMENTS
echo ==========================================
echo.
echo Current Whisper model (medium.en): ~8.7GB VRAM
echo Pyannote speaker diarization: ~2GB VRAM
echo Total required for advanced mode: ~11GB VRAM
echo.
echo Your RTX 3060 Ti (8GB) analysis:
echo - Whisper only: ✓ Supported
echo - Whisper + Pyannote: ⚠ May require CPU fallback
echo - CPU fallback available for pyannote if needed
echo.

echo ==========================================
echo TESTING CHECKLIST
echo ==========================================
echo.
echo 1. Run python main.py
echo 2. Check "Available GPU memory" in console output
echo 3. Try enabling "High-accuracy speaker diarization"
echo 4. Monitor GPU memory usage during recording
echo 5. Check performance metrics in session reports
echo.

echo Installation complete!
echo.
echo To test: python main.py
echo.
pause