# Amanuensis V2 - Therapy Transcription Tool

A professional therapy session transcription tool with local Whisper transcription for HIPAA compliance.

## Features
- Single-window desktop application
- Dual-channel audio capture (therapist mic + system audio)
- Local Whisper transcription (no cloud audio)
- Live transcript display with speaker separation
- Session file storage with timestamps
- Professional reliability for therapy sessions

## Installation

1. Install Python 3.10 or higher
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python main.py
   ```

## Usage

1. Select your microphone and system audio devices
2. Click "Start Recording" to begin session
3. Watch live transcript appear with [THERAPIST]/[CLIENT] labels
4. Click "Stop Recording" to end session and save transcript
5. Find saved transcript in the `sessions/` folder

## Requirements
- Python 3.10+
- Microphone access
- System audio capture capability
- Sufficient disk space for audio files and transcripts
# Amanuensis
