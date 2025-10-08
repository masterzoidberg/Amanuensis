# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Amanuensis V2 is a professional therapy session transcription tool designed for HIPAA compliance. It uses local Whisper transcription to ensure audio data never leaves the device. The application captures audio from a microphone and provides live transcription with speaker identification for therapy sessions.

## Development Commands

### Running the Application
```bash
python main.py
```

### Installation
```bash
pip install -r requirements.txt
```

**Note**: The application now uses SoundCard + faster-whisper with Silero VAD for production-grade performance and hallucination prevention.

### Windows Shortcuts
- `run.bat` - Start the application
- `install.bat` - Install dependencies with error checking

## Architecture

### Single-File Architecture
The entire application is contained in `main.py` as a monolithic MVP implementation. This design choice prioritizes:
- Rapid development and deployment
- Simplified debugging
- Easy maintenance for a focused use case

### Key Components

**AmanuensisApp Class** - Main application controller that manages:
- GUI using CustomTkinter
- Audio recording with SoundCard (explicit device selection)
- faster-whisper + Silero VAD transcription pipeline
- Performance monitoring and session management

### Audio Processing Pipeline

1. **Recording**: SoundCard explicit device selection with 100ms chunks
2. **Device Selection**: `get_microphone('TONOR')` style selection to avoid webcam mic conflicts
3. **Buffer Accumulation**: 15-20 second windows for optimal accuracy (configurable)
4. **VAD Filtering**: Silero VAD pre-filters audio to prevent hallucinations on silence/noise
5. **Transcription**: faster-whisper Medium.en model with GPU optimization (float16)
6. **Performance Monitoring**: Real-time RTF and GPU VRAM tracking

### Key Settings

**Audio Quality (Optimized for Stable Capture)**:
- Sample rate: Auto-detected (16000/44100/48000 Hz) for hardware compatibility
- Format: np.float32 (high precision)
- Buffer duration: 15-20 seconds (optimal window)
- SoundCard blocksize: 8192 samples (large buffers prevent underruns)
- Recording chunks: 200ms (increased from 100ms for stability)

**faster-whisper Configuration**:
- Model: "medium.en" (English-only for better performance)
- Compute type: "float16" (GPU) or "int8" (CPU)
- VAD filter: True (dual VAD with Silero + Whisper)
- Beam size: 5 for improved accuracy
- Temperature: 0.0 for deterministic output

**Silero VAD Parameters**:
- Min speech duration: 500ms
- Min silence duration: 100ms
- Speech padding: 200ms

### Threading Model

- **Main Thread**: GUI and user interaction
- **Recording Thread**: SoundCard continuous capture with buffer accumulation
- **Processing Threads**: VAD + Whisper transcription (one per buffer)
- **Performance Monitoring**: RTF, GPU VRAM, CPU usage tracking
- **Queue System**: Thread-safe transcript updates

### Performance Targets

- **Real-Time Factor**: <2.0x (target 1-2x for 50-minute sessions)
- **Latency**: 15-20 second processing windows
- **Accuracy**: Medium.en model + VAD filtering prevents hallucinations
- **Device Compatibility**: Explicit SoundCard device selection avoids conflicts

### System Audio Capture

- **SoundCard WASAPI**: Native loopback without Stereo Mix dependency
- **Explicit Selection**: Avoid webcam mic conflicts with targeted device selection
- **Dual-Channel**: [THERAPIST] mic + [CLIENT] system audio separation
- **Production Ready**: Zero-configuration deployment for therapists

### File Structure

- `sessions/` - Saved transcript files with timestamps and performance reports
- `sessions/performance_*.log` - Detailed performance logs per session
- `debug_audio/` - Audio buffer saves for debugging (WAV format)
- `requirements.txt` - Python dependencies (SoundCard, faster-whisper, silero-vad, torch, etc.)
- `main.py` - Complete application code

## Performance Monitoring

The application tracks and logs:
- **RTF (Real-Time Factor)**: Processing time / audio duration (target <2.0x)
- **GPU VRAM Usage**: Memory consumption during inference
- **CPU Usage**: System resource utilization
- **Processing Times**: Per-buffer transcription duration
- **Audio Discontinuities**: WASAPI buffer underruns and data gaps
- **Audio Quality Assessment**: Excellent/Good/Fair/Poor based on discontinuity count
- **System Configuration**: Power plan, audio service status, sample rate compatibility
- **Session Reports**: Comprehensive performance summaries saved with transcripts

## Development Notes

- SoundCard provides explicit device selection to avoid webcam mic conflicts
- Silero VAD prevents hallucinations on silence and background noise
- faster-whisper Medium.en model optimized for English-only therapy sessions
- GPU acceleration with float16 precision for real-time performance
- Dual-channel architecture with [THERAPIST]/[CLIENT] speaker separation
- 15-20 second buffer windows balance accuracy and latency
- Comprehensive error handling and performance monitoring

## Audio Stability Optimizations

- **Auto Sample Rate Detection**: Tests 16kHz, 44.1kHz, 48kHz for hardware compatibility
- **Large Buffer Sizes**: 8192-sample blocks prevent WASAPI underruns
- **Discontinuity Handling**: Graceful recovery with silence insertion and quality tracking
- **System Configuration Check**: Windows power plan and audio service validation
- **Performance Monitoring**: Real-time discontinuity counting and audio quality assessment
- **Error Recovery**: Continues recording with degraded quality rather than failing