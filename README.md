# Amanuensis - AI-Assisted Therapy Session Assistant

<div align="center">

**Secure Desktop Application for Therapists**

*Record • Transcribe • Analyze*

![Python](https://img.shields.io/badge/python-v3.8+-blue.svg)
![Kivy](https://img.shields.io/badge/GUI-Kivy-green.svg)
![Security](https://img.shields.io/badge/security-encrypted-red.svg)
![License](https://img.shields.io/badge/license-private-yellow.svg)

</div>

## Overview

Amanuensis is a secure desktop application designed specifically for therapists to enhance their practice through AI-assisted session documentation and analysis. Built with CustomTkinter for a professional, medical-software appearance, it provides dual-channel audio recording, automatic transcription with speaker identification, and intelligent analysis of therapeutic interactions while maintaining the highest standards of client privacy and data security.

### Key Features

🎙️ **Dual-Channel Recording**
- Therapist microphone capture (Channel 1)
- System audio capture for telehealth sessions (Channel 2)
- 3-minute rolling buffer for immediate analysis
- Support for couple and family therapy (multi-speaker)

🤖 **AI-Powered Analysis**
- Automatic transcription using OpenAI Whisper
- Speaker identification and separation
- Therapeutic insights using Anthropic Claude
- Real-time analysis of session dynamics

🔒 **Enterprise-Grade Security**
- Military-grade API key encryption
- Local-only data storage (no cloud sync)
- HIPAA-compliant data handling
- Automatic cleanup of sensitive data

👥 **Multi-Speaker Support**
- Individual, couple, and family therapy modes
- Automatic speaker diarization
- Manual speaker correction capabilities
- Speaker-specific therapeutic insights

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Application**
   ```bash
   python run_amanuensis.py
   ```
   or
   ```bash
   python amanuensis_ctk.py
   ```

3. **Configure API Keys**
   - Enter OpenAI API key for transcription
   - Enter Anthropic API key for analysis
   - Set up master password for encryption

4. **Setup Audio Devices**
   - Select therapist microphone
   - Configure system audio (Stereo Mix for Zoom)
   - Test audio levels

## System Requirements

- **OS**: Windows 10/11 (primary), macOS/Linux (supported)
- **Python**: 3.8 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 1GB free space for session data
- **Audio**: USB microphone, audio interface, or built-in mic
- **Network**: Internet connection for AI analysis
- **GUI**: CustomTkinter 5.2.0+ for modern, professional interface

## Architecture

```
┌─────────────────┬─────────────────┐
│ Audio Recording │ AI Processing   │
├─────────────────┼─────────────────┤
│ • Dual Channel  │ • Whisper API   │
│ • Rolling Buffer│ • Claude API    │
│ • Speaker ID    │ • Local Analysis│
└─────────────────┴─────────────────┘
┌─────────────────────────────────────┐
│ Secure Data Layer                   │
├─────────────────────────────────────┤
│ • Encrypted Storage                 │
│ • Session Management                │
│ • Privacy Controls                  │
└─────────────────────────────────────┘
```

## Core Components

### `amanuensis_ctk.py` - Main Application
- CustomTkinter-based professional GUI interface
- Session management and workflow
- Real-time audio monitoring
- Analysis result display
- Non-modal settings windows for stability

### `audio_manager.py` - Audio Processing
- Dual-channel audio capture
- Rolling buffer management
- Device configuration
- Volume level monitoring

### `config_manager.py` - Security Layer
- API key encryption/decryption
- Secure configuration storage
- Master password protection
- Memory cleanup procedures

### `speaker_manager.py` - Session Management
- Multi-speaker session handling
- Transcript storage and retrieval
- Speaker identification
- Session history tracking

### `api_manager.py` - AI Integration
- OpenAI Whisper integration
- Anthropic Claude analysis
- Secure API communication
- Response processing

## Usage Workflow

### 1. Pre-Session Setup
```
Configure Devices → Test Audio → Set Client Count → Start Recording
```

### 2. During Session
```
Monitor Levels → Take Notes → Analyze Segments → Review Insights
```

### 3. Post-Session
```
Stop Recording → Final Analysis → Save Notes → Export Data
```

## Security Features

### Data Protection
- **API Keys**: AES-256 encrypted with PBKDF2 key derivation
- **Session Data**: Local SQLite database with encryption
- **Audio Files**: Temporary storage with automatic cleanup
- **Network**: HTTPS-only API communication

### Privacy Controls
- **Local Storage**: No cloud synchronization or external storage
- **Access Control**: Master password required for application access
- **Data Retention**: Therapist-controlled retention policies
- **Client Consent**: Built-in consent management and documentation

### Compliance Features
- **HIPAA Considerations**: Local storage and encryption support compliance
- **Audit Trail**: Comprehensive session and access logging
- **Data Minimization**: Only necessary data collected and stored
- **Right to Deletion**: Easy client data removal procedures

## AI Analysis Capabilities

### Therapeutic Insights
- **Emotional Themes**: Identification of key emotional patterns
- **Communication Dynamics**: Analysis of therapist-client interactions
- **Progress Indicators**: Session-over-session progress tracking
- **Intervention Opportunities**: Suggestions for therapeutic techniques

### Multi-Speaker Analysis
- **Individual Insights**: Separate analysis for each family member
- **Relationship Dynamics**: Interaction patterns between speakers
- **Communication Styles**: Individual communication preferences
- **Therapeutic Engagement**: Participation levels and engagement metrics

## Audio Setup Guide

### Windows Stereo Mix Configuration
1. Right-click sound icon → Sounds → Recording tab
2. Right-click empty area → Show Disabled Devices
3. Enable "Stereo Mix" or "What U Hear"
4. Set as default recording device for system audio

### Alternative: Virtual Audio Cable
- Install VB-Audio Virtual Cable (free)
- Route Zoom audio through virtual cable
- Use cable output as system audio input

### Professional Audio Interfaces
- Connect therapist mic to Input 1
- Connect system audio to Input 2
- Configure as separate mono channels

## Documentation

- **[Setup Instructions](SETUP_INSTRUCTIONS.md)** - Detailed installation and configuration
- **[Security Documentation](SECURITY_DOCUMENTATION.md)** - Complete security architecture
- **[Privacy Consent Template](PRIVACY_CONSENT_TEMPLATE.md)** - Client consent forms

## API Services

### OpenAI Whisper
- **Purpose**: Audio transcription with speaker identification
- **Model**: whisper-1
- **Features**: Multi-language support, high accuracy
- **Pricing**: ~$0.006 per minute of audio

### Anthropic Claude
- **Purpose**: Therapeutic analysis and insights
- **Model**: claude-3-5-sonnet-20241022
- **Features**: Contextual understanding, therapeutic expertise
- **Pricing**: ~$0.015 per 1K tokens

## Development

### Project Structure
```
Amanuensis/
├── amanuensis_ctk.py          # Main CustomTkinter application
├── run_amanuensis.py          # Application launcher with error handling
├── audio_manager.py           # Audio processing
├── config_manager.py          # Security and configuration
├── speaker_manager.py         # Session and speaker management
├── api_manager.py            # AI service integration
├── requirements.txt          # Python dependencies
├── SETUP_INSTRUCTIONS.md     # Installation guide
├── SECURITY_DOCUMENTATION.md # Security details
├── PRIVACY_CONSENT_TEMPLATE.md # Client consent
└── temp_recordings/          # Temporary audio files
```

### Key Dependencies
```python
customtkinter>=5.2.0          # Professional GUI framework
pyaudio>=0.2.11               # Audio recording
openai>=1.0.0                 # Whisper API
anthropic>=0.7.0              # Claude API
cryptography>=41.0.0          # Security and encryption
numpy>=1.24.0                 # Audio processing
pillow>=10.0.0                # Image processing for CustomTkinter
```

## Professional Use

### Clinical Applications
- **Individual Therapy**: Single client session analysis
- **Couples Therapy**: Relationship dynamics and communication patterns
- **Family Therapy**: Multi-generational interaction analysis
- **Group Therapy**: Participation and engagement tracking

### Therapeutic Benefits
- **Session Insights**: Deeper understanding of client presentations
- **Progress Tracking**: Objective measures of therapeutic progress
- **Intervention Planning**: Data-driven treatment recommendations
- **Documentation Support**: Enhanced clinical documentation

### Professional Considerations
- **Clinical Judgment**: AI insights supplement, never replace, professional assessment
- **Client Consent**: Always obtain informed consent for recording and analysis
- **Data Security**: Follow all applicable privacy and security regulations
- **Ethical Use**: Maintain professional boundaries and ethical standards

## Support and Contributing

### Getting Help
- Review documentation for setup and troubleshooting
- Check security documentation for privacy concerns
- Verify audio setup for common technical issues

### Professional Requirements
- Valid therapy license required for clinical use
- HIPAA compliance responsibility remains with practitioner
- Client consent required for all recording and analysis
- Regular security reviews and updates recommended

---

**Amanuensis** - Enhancing therapeutic practice through secure AI assistance

*"The skilled assistant to the therapeutic process"*