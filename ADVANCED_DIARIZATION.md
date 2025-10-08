# Advanced Speaker Diarization Implementation

## Overview

This implementation adds a two-stage pipeline using Whisper + pyannote.audio for improved speaker diarization in therapy transcription sessions. While it introduces a 20-30 second latency, it significantly improves speaker identification accuracy compared to the standard dual-channel approach.

## Architecture

### Two-Stage Processing Pipeline

1. **Stage 1: Whisper Transcription**
   - Combines microphone and system audio for better accuracy
   - Uses existing faster-whisper Medium.en model
   - Maintains VAD filtering for quality

2. **Stage 2: Pyannote Speaker Diarization**
   - Runs speaker diarization on 2-minute audio chunks
   - Uses official pyannote/speaker-diarization-3.1 model
   - GPU-optimized with CPU fallback

3. **Stage 3: Speaker Alignment**
   - Aligns Whisper text segments with pyannote speaker segments
   - Calculates speaker overlap confidence scores
   - Maps speakers to [THERAPIST]/[CLIENT] labels

### Audio Buffering System

- **Standard Buffer**: 18-second chunks for real-time processing
- **Diarization Buffer**: Configurable (30s, 1min, 90s, 2min) for latency vs accuracy trade-off
- **Overlap Management**: Dynamic overlap (15% of buffer size, 5-15s range)
- **Dual Processing**: Both pipelines run simultaneously when enabled

## GPU Memory Management

### Requirements
- **Whisper Medium.en**: ~8.7GB VRAM
- **Pyannote Diarization**: ~2GB VRAM
- **Total**: ~11GB VRAM for optimal performance

### RTX 3060 Ti Compatibility (8GB VRAM)
- **Whisper Only**: ✅ Fully supported
- **Whisper + Pyannote**: ⚠️ CPU fallback for pyannote
- **Automatic Detection**: System detects memory constraints
- **Graceful Degradation**: Falls back to CPU or disables advanced mode

### Memory Management Features
- Pre-loading memory checks
- Runtime memory monitoring
- Automatic GPU/CPU device selection
- Error handling with fallback strategies

## Installation

### Prerequisites
```bash
# Install base dependencies
pip install -r requirements.txt

# Install advanced dependencies
pip install pyannote.audio>=3.1.0 librosa>=0.10.0
```

### HuggingFace Setup (Required for Production)
1. Create account at https://huggingface.co/
2. Accept license at https://huggingface.co/pyannote/speaker-diarization-3.1
3. Generate access token at https://huggingface.co/settings/tokens
4. Login: `huggingface-cli login`

### Quick Setup
```bash
# Use provided installation script
install_advanced.bat
```

## Usage

### Enabling Advanced Diarization
1. Launch application: `python main.py`
2. Check "High-accuracy speaker diarization (2min delay)" checkbox
3. Verify status shows "✓ Models loaded, GPU optimized"
4. Start recording session

### Performance Monitoring
- Real-time GPU memory usage logging
- Advanced diarization RTF tracking
- Speaker alignment confidence metrics
- Comprehensive session reports

### Settings and Configuration
- **Buffer Duration**: Configurable via dropdown (30s/1min/90s/2min)
  - **30 seconds**: Low latency, good accuracy, ideal for interactive sessions
  - **1 minute**: Balanced approach, recommended default for most therapy sessions
  - **90 seconds**: Higher accuracy, suitable for complex speaker patterns
  - **2 minutes**: Maximum accuracy, best for research and detailed analysis
- **Processing Mode**: GPU preferred, CPU fallback
- **Speaker Mapping**: Most active speaker → THERAPIST
- **Overlap Handling**: Dynamic overlap based on buffer size (15% ratio)

## Error Handling and Fallbacks

### Automatic Fallback Scenarios
1. **GPU Memory Exhaustion**: Disables advanced mode, continues with standard
2. **Pyannote Load Failure**: CPU fallback, then disable if fails
3. **Processing Errors**: Falls back to standard channel-based processing
4. **Model Download Issues**: Graceful degradation with user notification

### Error Recovery
- Detailed error logging with stack traces
- Specific error handling for CUDA OOM, pyannote errors
- Session continuity maintained during failures
- User notification of mode changes

## Performance Metrics

### Tracked Metrics
- **RTF Values**: Real-time factor for both standard and advanced processing
- **GPU Memory Usage**: Before/during/after model loading and processing
- **Speaker Alignment Accuracy**: Confidence scores for speaker assignments
- **Processing Latency**: Time from audio capture to transcript output
- **Chunk Processing Count**: Advanced vs standard chunk statistics

### Performance Reports
Session reports include:
- Standard processing performance
- Advanced diarization performance (when enabled)
- GPU memory utilization
- Speaker alignment accuracy percentages
- Audio quality assessment

## Testing and Validation

### Testing Checklist
1. ✅ GPU memory detection and reporting
2. ✅ Model loading with memory constraints
3. ✅ Two-stage processing pipeline
4. ✅ Speaker alignment and mapping
5. ✅ Error handling and fallbacks
6. ✅ Performance monitoring
7. ✅ Session report generation

### Validation Commands
```python
# Test GPU memory
app.log_memory_usage("test")

# Test advanced processing (requires audio)
app.process_advanced_diarization(mic_audio, sys_audio)

# Check performance stats
print(app.get_performance_summary())
```

## Technical Implementation Details

### Key Functions
- `load_pyannote_pipeline()`: Model loading with memory management
- `process_advanced_diarization()`: Two-stage processing pipeline
- `align_whisper_with_pyannote()`: Speaker-text alignment logic
- `map_speakers_to_labels()`: Speaker ID to label mapping
- `log_memory_usage()`: GPU memory monitoring

### Integration Points
- Audio recording loop: Dual buffer accumulation
- Processing threads: Parallel standard/advanced processing
- UI controls: Settings toggle with validation
- Performance tracking: Enhanced metrics collection
- Session reporting: Advanced statistics inclusion

### Speaker Mapping Strategy
1. **Duration-based**: Assign most active speaker as THERAPIST
2. **Confidence-weighted**: Use alignment confidence for validation
3. **Consistency**: Maintain mapping across processing chunks
4. **Fallback**: Handle single speaker or unknown speaker scenarios

## Troubleshooting

### Common Issues

**"Pyannote.audio not available"**
- Install: `pip install pyannote.audio`
- Verify: Check for successful installation

**"Failed to load pyannote models"**
- Requires HuggingFace token for official models
- Check internet connection for model download
- Verify HF account has accepted model license

**"GPU memory error"**
- Expected on RTX 3060 Ti (8GB) - will use CPU fallback
- Close other GPU-intensive applications
- Consider using CPU mode for pyannote

**"Advanced diarization disabled"**
- Check GPU memory availability
- Verify model loading succeeded
- Review console output for specific errors

### Performance Optimization
- Use SSD for model caching
- Ensure adequate system RAM (16GB+)
- Close unnecessary background applications
- Use dedicated GPU for optimal performance

## Future Enhancements

### Planned Improvements
1. **Adaptive Buffer Sizing**: Dynamic buffer adjustment based on GPU memory
2. **Custom Speaker Models**: Fine-tuned models for therapy sessions
3. **Real-time Diarization**: Reduced latency processing
4. **Speaker Recognition**: Persistent speaker identification across sessions
5. **Quality Metrics**: Advanced speaker change detection and validation

### Configuration Options
- Adjustable buffer sizes
- Speaker mapping preferences
- Performance vs accuracy trade-offs
- Custom model path support