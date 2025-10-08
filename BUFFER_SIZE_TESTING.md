# Buffer Size Testing Guide

## Quick Testing for Different Buffer Sizes

### Testing Setup
1. Launch application: `python main.py`
2. Enable "High-accuracy speaker diarization"
3. Test each buffer size option with different scenarios

### Buffer Size Options

#### 30 Seconds (Ultra-Fast)
- **Best for**: Real-time feedback, interactive sessions
- **Latency**: 30-40 seconds
- **Expected RTF**: 0.8-1.5x (depending on GPU)
- **Test scenario**: Quick back-and-forth conversation
- **Watch for**: Quick speaker identification, possible missed transitions

#### 1 Minute (Recommended Default)
- **Best for**: Standard therapy sessions
- **Latency**: 60-70 seconds
- **Expected RTF**: 1.0-2.0x
- **Test scenario**: Normal conversation with moderate speaker changes
- **Watch for**: Good balance of speed and accuracy

#### 90 Seconds (High Accuracy)
- **Best for**: Complex conversations with overlapping speech
- **Latency**: 90-100 seconds
- **Expected RTF**: 1.2-2.5x
- **Test scenario**: Multiple speakers, interruptions, overlapping speech
- **Watch for**: Better handling of complex speaker patterns

#### 2 Minutes (Maximum Accuracy)
- **Best for**: Research analysis, detailed post-session review
- **Latency**: 120-130 seconds
- **Expected RTF**: 1.5-3.0x
- **Test scenario**: Long conversation segments with subtle speaker changes
- **Watch for**: Highest speaker identification accuracy

### Performance Testing Checklist

#### Memory Usage Test
```
1. Launch app and note "Available GPU memory"
2. Enable advanced diarization
3. Check "GPU Memory after Whisper loading"
4. Check "GPU Memory after Pyannote loading" (if successful)
5. Start recording and monitor memory during processing
```

#### Latency Comparison Test
```
1. Record same 5-minute conversation with each buffer size
2. Note processing times in console output
3. Compare RTF values in session reports
4. Evaluate speaker accuracy by reviewing transcripts
```

#### Accuracy Validation Test
```
1. Use test audio with known speaker segments
2. Compare speaker assignments across buffer sizes
3. Check speaker alignment confidence scores
4. Validate [THERAPIST]/[CLIENT] mapping accuracy
```

### Expected Performance Ranges

#### RTX 3060 Ti (8GB) Performance Expectations
- **30s buffer**: RTF 0.8-1.2x (GPU), 2.0-3.0x (CPU fallback)
- **1min buffer**: RTF 1.0-1.5x (GPU), 2.5-4.0x (CPU fallback)
- **90s buffer**: RTF 1.2-2.0x (GPU), 3.0-5.0x (CPU fallback)
- **2min buffer**: RTF 1.5-2.5x (GPU), 4.0-6.0x (CPU fallback)

#### GPU Memory Usage (Approximate)
- Whisper only: ~8.7GB
- Whisper + Pyannote (GPU): ~10.7GB (may trigger CPU fallback)
- Whisper + Pyannote (CPU): ~8.7GB GPU + system RAM for pyannote

### Testing Commands

#### Console Testing
```python
# Check current buffer configuration
print(f"Buffer size: {app.diarization_buffer_size}s")
print(f"Overlap size: {app.get_diarization_overlap_size()}s")

# Get buffer recommendations
recommendations = app.get_buffer_size_recommendations()
for size, info in recommendations.items():
    print(f"{size}: {info['trade_off']}")

# Monitor memory during operation
app.log_memory_usage("during_processing")
```

#### Performance Validation
```python
# After session, check advanced diarization stats
if app.performance_stats['advanced_diarization_chunks'] > 0:
    avg_rtf = np.mean(app.performance_stats['advanced_diarization_rtf'])
    print(f"Advanced RTF: {avg_rtf:.2f}x")

    if app.performance_stats['speaker_alignment_accuracy']:
        avg_accuracy = np.mean(app.performance_stats['speaker_alignment_accuracy'])
        print(f"Speaker accuracy: {avg_accuracy:.1%}")
```

### Troubleshooting Buffer Size Issues

#### "Processing too slow"
- Try smaller buffer size (30s or 1min)
- Check if pyannote is using CPU fallback
- Verify GPU memory availability

#### "Speaker accuracy poor"
- Try larger buffer size (90s or 2min)
- Check speaker alignment confidence scores
- Verify adequate overlap between chunks

#### "GPU memory errors"
- Reduce buffer size to decrease memory pressure
- Allow automatic CPU fallback for pyannote
- Close other GPU applications

### Recommendations by Use Case

#### Real-time Therapy Sessions
**Recommended**: 30 seconds or 1 minute
- Faster feedback for therapist
- Good enough accuracy for live session
- Can be post-processed with longer buffers if needed

#### Session Recording & Analysis
**Recommended**: 90 seconds or 2 minutes
- Maximum speaker identification accuracy
- Better handling of complex conversation patterns
- Suitable for detailed post-session review

#### Research & Training
**Recommended**: 2 minutes
- Highest quality speaker diarization
- Better for creating training datasets
- Most accurate for research analysis

### Session Report Analysis

Look for these metrics in session reports:
- **Buffer Size**: Confirms active buffer setting
- **Overlap**: Shows dynamic overlap calculation
- **Advanced RTF**: Processing speed for advanced chunks
- **Speaker Alignment Accuracy**: Confidence in speaker assignments
- **Chunks Processed**: Number of advanced diarization chunks

### Quick Validation Test

1. **30-second test**: Record 2 minutes, should produce ~3-4 advanced chunks
2. **1-minute test**: Record 3 minutes, should produce ~2-3 advanced chunks
3. **2-minute test**: Record 5 minutes, should produce ~2-3 advanced chunks

Each should show different RTF and accuracy characteristics in the session report.