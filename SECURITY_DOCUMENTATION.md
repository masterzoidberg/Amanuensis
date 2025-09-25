# Amanuensis Security Documentation

## Security Architecture Overview

Amanuensis implements multiple layers of security to protect sensitive therapeutic data throughout the recording, transcription, and analysis workflow.

## Threat Model

### Protected Assets
- **Client Audio Recordings**: Raw therapy session audio
- **Session Transcripts**: AI-generated transcriptions with speaker identification
- **AI Analysis**: Therapeutic insights and recommendations
- **API Keys**: OpenAI and Anthropic service credentials
- **Session Metadata**: Client counts, session notes, timestamps

### Threat Actors
- **Unauthorized Local Access**: Users without permission accessing therapist's computer
- **Network Eavesdropping**: Interception of API communications
- **Malicious Software**: Malware attempting to access session data
- **Data Breach**: Accidental exposure of sensitive files
- **API Key Theft**: Unauthorized use of service credentials

### Attack Vectors
- **File System Access**: Direct access to data files
- **Memory Dumps**: Extraction from system memory
- **Network Traffic**: Interception of API calls
- **Configuration Files**: Exposure of unencrypted settings
- **Temporary Files**: Access to audio processing artifacts

## Security Controls

### 1. API Key Protection

#### Encryption at Rest
```python
# Implementation: config_manager.py
- Uses Fernet (AES 128) symmetric encryption
- PBKDF2 key derivation with 100,000 iterations
- SHA-256 hashing algorithm
- 16-byte random salt per installation
- Master password required for decryption
```

#### Key Management
- **Storage**: API keys encrypted in `config.json`
- **Salt File**: Encryption salt stored separately in `config.json.salt`
- **Memory Protection**: Keys cleared from memory after use
- **Access Control**: Master password required for key access

#### Implementation Details
```python
def _derive_key(self, password: str, salt: bytes = None) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt
```

### 2. Session Data Protection

#### Database Encryption
- **SQLite Database**: Local storage only
- **Sensitive Fields**: Transcript text, session notes, speaker names
- **Access Control**: File-level permissions restrict access
- **No Cloud Storage**: All data remains on local machine

#### Data Schema Security
```sql
-- Transcript table with metadata separation
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    timestamp REAL NOT NULL,
    speaker_name TEXT NOT NULL,  -- Pseudonymized
    text TEXT NOT NULL,          -- Therapeutic content
    confidence REAL DEFAULT 0.0
);
```

### 3. Audio Processing Security

#### Temporary File Handling
```python
# Implementation: audio_manager.py
def cleanup(self):
    try:
        temp_files = glob.glob("temp_recordings/*.wav")
        for file in temp_files:
            os.remove(file)  # Secure deletion
    except:
        pass
```

#### Buffer Management
- **Memory Buffers**: Automatic cleanup on session end
- **File Permissions**: Temporary files restricted to application user
- **Deletion Policy**: Automatic cleanup of processing artifacts

### 4. API Communication Security

#### Transport Security
- **HTTPS Only**: All API communications use TLS 1.2+
- **Certificate Validation**: Server certificates verified
- **No Plaintext**: Audio and text data encrypted in transit

#### API Key Usage
```python
def cleanup(self):
    try:
        if hasattr(self.openai_client, 'api_key'):
            self.openai_client.api_key = None  # Clear from memory
        if hasattr(self.anthropic_client, 'api_key'):
            self.anthropic_client.api_key = None
    except:
        pass
```

#### Data Retention Policies
- **OpenAI**: Audio files processed but not stored per API terms
- **Anthropic**: Text analyzed but not retained per API terms
- **Local Only**: All persistent data stored locally

### 5. Application Security

#### Input Validation
```python
def validate_api_keys(self) -> dict:
    required_keys = ['openai', 'anthropic']
    api_keys = self.config.get('api_keys', {})
    validation_result = {}
    for key in required_keys:
        validation_result[key] = bool(api_keys.get(key, '').strip())
    return validation_result
```

#### Error Handling
- **No Sensitive Data in Logs**: API keys never logged
- **Graceful Degradation**: Failures don't expose sensitive information
- **User Feedback**: Generic error messages to prevent information leakage

#### Session Management
```python
def end_session(self, session_id: int, notes: str = ""):
    # Secure session cleanup
    self.current_session_speakers = {}
    # Database updates with parameterized queries
    cursor.execute('''
        UPDATE sessions SET status = 'completed', notes = ? WHERE id = ?
    ''', (notes, session_id))
```

## File System Security

### Directory Structure
```
Amanuensis/
├── config.json              # Encrypted API keys (sensitive)
├── config.json.salt          # Encryption salt (sensitive)
├── session_data.db           # Encrypted session data (sensitive)
├── temp_recordings/          # Temporary audio files (auto-cleanup)
│   ├── session_*_therapist.wav
│   └── session_*_client.wav
├── *.py                      # Application code (non-sensitive)
└── *.md                      # Documentation (non-sensitive)
```

### File Permissions
- **Sensitive Files**: Restricted to application user only
- **Temporary Directory**: Automatic cleanup on exit
- **Database File**: SQLite with file-level access control

### Gitignore Security
```gitignore
# Sensitive configuration and data
config.json
*.key
session_data.db
audio_temp/

# Temporary processing files
*.wav
*.mp3
temp_recordings/
```

## Network Security

### API Endpoints
- **OpenAI Whisper**: `https://api.openai.com/v1/audio/transcriptions`
- **Anthropic Claude**: `https://api.anthropic.com/v1/messages`
- **TLS Requirements**: Minimum TLS 1.2, certificate pinning recommended

### Data Flow Security
```
1. Audio Recording (Local) → 2. Temporary Files (Local) →
3. HTTPS Upload (Encrypted) → 4. API Processing (External) →
5. HTTPS Response (Encrypted) → 6. Local Database (Encrypted)
```

### Network Monitoring
- **No Persistent Connections**: API calls are request/response only
- **Timeout Controls**: Prevent hanging connections
- **Retry Logic**: Secure handling of network failures

## Compliance Considerations

### HIPAA Compliance Factors
- **Local Storage**: No cloud storage reduces HIPAA risk
- **Encryption**: Data encrypted at rest and in transit
- **Access Control**: Password-protected application access
- **Audit Trail**: Session logging for compliance tracking

### Professional Standards
- **Client Consent**: Template provided for informed consent
- **Data Minimization**: Only necessary data collected and stored
- **Retention Control**: Therapist controls data retention periods
- **Access Logging**: Track who accesses what data when

## Security Monitoring

### Logging Strategy
```python
# Secure logging practices
Logger.info(f"Session {session_id} started")  # OK - no sensitive data
Logger.error(f"API key validation failed")     # OK - no key content
# NEVER: Logger.debug(f"API key: {api_key}")   # SECURITY VIOLATION
```

### Audit Events
- **Session Start/End**: Timestamp and duration
- **API Calls**: Success/failure without sensitive content
- **Configuration Changes**: Settings modifications
- **Access Attempts**: Failed authentication attempts

### Threat Detection
- **File Integrity**: Monitor config files for unauthorized changes
- **Network Anomalies**: Unusual API usage patterns
- **Process Monitoring**: Detect unauthorized access attempts

## Incident Response

### Security Incident Categories
1. **API Key Compromise**: Unauthorized use of service credentials
2. **Data Breach**: Unauthorized access to client data
3. **System Compromise**: Malware or unauthorized system access
4. **Network Interception**: Man-in-the-middle attacks

### Response Procedures
1. **Immediate**: Isolate affected systems, change API keys
2. **Assessment**: Determine scope and impact of breach
3. **Notification**: Inform affected clients per legal requirements
4. **Remediation**: Apply security patches, update procedures

### Recovery Process
1. **System Restoration**: Clean installation if compromised
2. **Data Recovery**: Restore from clean backups
3. **Key Rotation**: Generate new API keys and master password
4. **Security Review**: Assess and improve security controls

## Security Best Practices

### For Therapists
1. **Strong Master Password**: Use complex, unique password for encryption
2. **System Updates**: Keep operating system and application updated
3. **Network Security**: Use secure, private networks for sessions
4. **Physical Security**: Secure computer when not in use
5. **Regular Backups**: Backup encrypted session data regularly

### For System Administrators
1. **Endpoint Protection**: Install and maintain antivirus software
2. **Firewall Configuration**: Block unnecessary network access
3. **User Account Control**: Limit administrator privileges
4. **Audit Logging**: Enable system-level security logging
5. **Vulnerability Management**: Regular security assessments

### For Development
1. **Code Review**: Security-focused code reviews
2. **Dependency Scanning**: Monitor for vulnerable dependencies
3. **Static Analysis**: Automated security code analysis
4. **Penetration Testing**: Regular security assessments
5. **Secure Development**: Follow OWASP secure coding practices

## Security Testing

### Automated Testing
```python
def test_api_key_encryption():
    """Verify API keys are properly encrypted"""
    config = SecureConfigManager()
    config.setup_encryption("test_password")
    config.set_api_key("test", "sensitive_key")

    # Verify key is not stored in plaintext
    with open("config.json", "rb") as f:
        encrypted_content = f.read()
        assert b"sensitive_key" not in encrypted_content
```

### Manual Security Tests
1. **File System**: Verify sensitive data not in plaintext files
2. **Memory**: Check for API keys in process memory dumps
3. **Network**: Monitor API communications for data leakage
4. **Error Handling**: Verify no sensitive data in error messages

### Third-Party Security
1. **API Providers**: Review OpenAI and Anthropic security practices
2. **Dependencies**: Monitor Python package vulnerabilities
3. **Operating System**: Apply security patches promptly

This security documentation should be reviewed and updated regularly as threats evolve and the application develops.