# Amanuensis Setup Instructions

## Overview
Amanuensis is a secure desktop application for therapists to record, transcribe, and analyze therapy sessions with AI assistance. It supports multi-speaker environments and provides secure handling of sensitive therapeutic data.

## Prerequisites

### System Requirements
- Windows 10/11 (primary support)
- Python 3.8 or higher
- Minimum 4GB RAM (8GB recommended)
- Audio interface or USB microphone
- Internet connection for AI analysis

### Required API Keys
- **OpenAI API Key**: For Whisper transcription service
- **Anthropic API Key**: For Claude analysis service

## Installation Steps

### 1. Install Python Dependencies
```bash
# Navigate to the project directory
cd Amanuensis

# Install required packages
pip install -r requirements.txt
```

### 2. Windows Audio Configuration

#### Enable Stereo Mix (Critical for Zoom/System Audio Capture)

1. **Right-click** the speaker icon in the system tray
2. Select **"Sounds"**
3. Click the **"Recording"** tab
4. **Right-click** in the empty area and select **"Show Disabled Devices"**
5. Find **"Stereo Mix"** or **"What U Hear"**
6. **Right-click** on "Stereo Mix" and select **"Enable"**
7. **Right-click** again and select **"Set as Default Device"**

#### Alternative: Use Virtual Audio Cable
If Stereo Mix is not available:

1. Download and install **VB-Audio Virtual Cable** (free)
2. Set **"CABLE Input"** as your default playback device during sessions
3. Use **"CABLE Output"** as the system audio input in Amanuensis

#### For Professional Audio Interfaces
- Use a dedicated USB audio interface with multiple inputs
- Connect therapist microphone to Input 1
- Connect Zoom audio output to Input 2
- Configure inputs as separate mono channels

### 3. API Key Configuration

#### Obtain API Keys

**OpenAI API Key:**
1. Visit https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-...`)

**Anthropic API Key:**
1. Visit https://console.anthropic.com/
2. Create a new API key
3. Copy the key (starts with `sk-ant-...`)

#### Configure in Amanuensis
1. Run the application: `python amanuensis.py`
2. On first launch, you'll see the setup dialog
3. Enter your API keys when prompted
4. Click "Save & Test" to verify connections

### 4. Audio Device Setup

#### Initial Audio Configuration
1. In Amanuensis, click **"Select Audio Devices"**
2. **Therapist Microphone**: Select your dedicated microphone
3. **System Audio**: Select "Stereo Mix" or virtual audio device
4. Click **"Test Audio Levels"** to verify both inputs are working
5. **Save** the configuration

#### Testing Audio Levels
- Speak into the therapist microphone - you should see activity in the "Mic" bar
- Play audio through Zoom/system - you should see activity in the "System" bar
- Both levels should be clearly visible before starting a session

## Usage Workflow

### 1. Pre-Session Setup
1. **Test Zoom Audio**: Ensure Zoom audio is playing through speakers/headphones
2. **Select Client Count**: Choose number of clients (1-6)
3. **Verify Audio Levels**: Both microphone and system audio should show activity
4. **Check API Status**: Footer should show "API: Connected"

### 2. During Session
1. **Start Recording**: Click "Start Recording" - button turns red
2. **Monitor Levels**: Watch volume bars to ensure audio capture
3. **Take Notes**: Use the session notes area for manual observations
4. **Analyze Segments**: Click "Analyze Last 3 Minutes" for real-time insights

### 3. Analysis Features
- **Real-time Transcription**: Automatic speaker separation
- **AI Insights**: Therapeutic themes, relationship dynamics
- **Follow-up Suggestions**: Questions for future sessions
- **Speaker-specific Analysis**: Individual client observations

### 4. Post-Session
- **Review Analysis**: Check AI insights and recommendations
- **Save Notes**: Session notes are automatically saved
- **Export Data**: Transcripts and analysis are stored locally

## Security Features

### Data Protection
- **API keys encrypted** at rest using military-grade encryption
- **Local data storage** - no cloud synchronization
- **Automatic cleanup** of temporary audio files
- **Memory protection** - sensitive data cleared after use

### Privacy Compliance
- **Client consent**: Always obtain written consent for recording
- **Data retention**: Follow your practice's data retention policies
- **Secure storage**: All session data encrypted in local database
- **Access control**: Master password required for application access

## Troubleshooting

### Common Audio Issues

**Problem**: No microphone input detected
- **Solution**: Check Windows privacy settings for microphone access
- **Solution**: Ensure correct microphone selected in device settings
- **Solution**: Try different USB port for USB microphones

**Problem**: No system audio (Zoom) detected
- **Solution**: Verify Stereo Mix is enabled and set as default
- **Solution**: Check Zoom audio settings - should output to speakers, not headphones
- **Solution**: Try Virtual Audio Cable as alternative

**Problem**: Audio levels very low
- **Solution**: Adjust microphone boost in Windows sound settings
- **Solution**: Increase Zoom audio volume
- **Solution**: Position microphone 6-12 inches from speaker

### API Issues

**Problem**: "API: Disconnected" in footer
- **Solution**: Verify API keys are entered correctly
- **Solution**: Check internet connection
- **Solution**: Confirm API key billing/credits are active

**Problem**: Transcription fails
- **Solution**: Check audio file quality and length
- **Solution**: Verify OpenAI API key has Whisper access
- **Solution**: Try shorter audio segments (1-2 minutes)

**Problem**: Analysis fails
- **Solution**: Check Anthropic API key validity
- **Solution**: Verify transcript text is not empty
- **Solution**: Try analysis with shorter sessions

### Performance Issues

**Problem**: Application crashes during recording
- **Solution**: Close other audio applications
- **Solution**: Reduce buffer duration in settings
- **Solution**: Check available disk space for temp files

**Problem**: Slow analysis processing
- **Solution**: Check internet connection speed
- **Solution**: Try analyzing shorter segments
- **Solution**: Verify API service status

## Best Practices

### Session Management
- **Consistent Setup**: Use the same audio configuration for all sessions
- **Regular Testing**: Test audio levels before each session
- **Backup Important Sessions**: Export critical session transcripts
- **Client Preparation**: Inform clients about recording and analysis

### Security Practices
- **Strong Master Password**: Use complex password for API key encryption
- **Regular Updates**: Keep application and dependencies updated
- **Secure Environment**: Use application only on secure, private computers
- **Data Backup**: Regularly backup session database to secure location

### Professional Use
- **Client Consent**: Always obtain written consent for AI analysis
- **Review AI Output**: Manually review all AI insights before using
- **Supplement, Don't Replace**: Use as tool to enhance, not replace, clinical judgment
- **Documentation**: Keep records of how AI insights influence treatment decisions

## Support and Updates

### Getting Help
- **Documentation**: Refer to this guide for common issues
- **Audio Setup**: Focus on Stereo Mix configuration for most problems
- **API Issues**: Verify keys and account status first

### Data Migration
If reinstalling or moving to new computer:
1. **Backup config.json.salt** (encryption salt file)
2. **Backup session_data.db** (session database)
3. **Export important session transcripts** to text files
4. **Reconfigure API keys** on new installation

### Version Updates
- **Backup data** before updating
- **Test audio setup** after updates
- **Verify API connections** after updates

## Legal and Ethical Considerations

### Client Consent
- **Written consent required** for recording and AI analysis
- **Explain data flow**: Local storage, AI analysis, no cloud sync
- **Right to refuse**: Clients can opt out of AI analysis
- **Data ownership**: Clarify who owns transcripts and analysis

### Professional Responsibility
- **Clinical judgment**: AI insights supplement, never replace, professional assessment
- **Bias awareness**: Be aware of potential AI biases in analysis
- **Confidentiality**: Ensure secure handling of all session data
- **Supervision**: Consider supervisory review of AI-assisted sessions

This setup ensures Amanuensis operates securely and effectively for professional therapeutic practice.