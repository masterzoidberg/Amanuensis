#!/usr/bin/env python3
"""
Enhanced Amanuensis Launcher
Main entry point for the enhanced transcription system
"""

import sys
import os
import time

def show_banner():
    """Show application banner"""
    print("=" * 60)
    print("")
    print("    AMANUENSIS ENHANCED - v2.0".center(60))
    print("")
    print("  Real-Time Local Transcription System".center(60))
    print("  Privacy-First • GPU Accelerated • HIPAA Ready".center(60))
    print("")
    print("=" * 60)
    print()

def check_system():
    """Check system compatibility"""
    print("System Compatibility Check")
    print("-" * 40)
    
    issues = []
    warnings = []
    
    # Python version
    python_version = sys.version_info
    print(f"Python: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version < (3, 8):
        issues.append("Python 3.8+ required")
    else:
        print("[OK] Python version OK")
    
    # Memory check
    try:
        import psutil
        memory_gb = psutil.virtual_memory().total / (1024**3)
        print(f"Memory: {memory_gb:.1f} GB")
        if memory_gb < 4:
            issues.append("Minimum 4GB RAM required")
        elif memory_gb < 8:
            warnings.append("8GB+ RAM recommended for better performance")
        else:
            print("[OK] Memory OK")
    except ImportError:
        warnings.append("Cannot check memory (psutil not installed)")
    
    # GPU check
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"GPU: {gpu_name}")
            print("[OK] CUDA GPU available - excellent performance expected")
        else:
            print("GPU: Not available")
            warnings.append("No GPU detected - CPU mode will be slower")
    except ImportError:
        warnings.append("Cannot check GPU (torch not installed)")
    
    # Storage check
    try:
        import shutil
        free_gb = shutil.disk_usage('.').free / (1024**3)
        print(f"Storage: {free_gb:.1f} GB free")
        if free_gb < 5:
            issues.append("Minimum 5GB free space required")
        elif free_gb < 20:
            warnings.append("20GB+ recommended for extensive sessions")
        else:
            print("[OK] Storage OK")
    except:
        warnings.append("Cannot check storage")
    
    print()
    
    # Show issues and warnings
    if issues:
        print("[ERROR] Critical Issues:")
        for issue in issues:
            print(f"   • {issue}")
        print()
        return False
    
    if warnings:
        print("[WARN] Warnings:")
        for warning in warnings:
            print(f"   • {warning}")
        print()
    
    return True

def check_dependencies():
    """Check required dependencies"""
    print(" Dependency Check")
    print("-" * 40)
    
    required_deps = [
        ("customtkinter", "UI Framework"),
        ("numpy", "Numerical Computing"),
        ("pyaudio", "Audio Processing"),
        ("faster_whisper", "Speech Recognition"),
        ("torch", "Deep Learning"),
        ("soundfile", "Audio File I/O"),
    ]
    
    optional_deps = [
        ("psutil", "System Monitoring"),
        ("openai", "Analysis Features"),
        ("anthropic", "Analysis Features"),
        ("cryptography", "Security"),
    ]
    
    missing_required = []
    missing_optional = []
    
    # Check required dependencies
    for package, description in required_deps:
        try:
            __import__(package)
            print(f"[OK] {package} - {description}")
        except ImportError:
            print(f"[ERROR] {package} - {description} (MISSING)")
            missing_required.append(package)

    # Check optional dependencies
    for package, description in optional_deps:
        try:
            __import__(package)
            print(f"[OK] {package} - {description}")
        except ImportError:
            print(f"[WARN] {package} - {description} (optional)")
            missing_optional.append(package)
    
    print()
    
    if missing_required:
        print("[ERROR] Missing Required Dependencies:")
        for dep in missing_required:
            print(f"   • {dep}")
        print()
        print("Install with:")
        print("   pip install -r requirements.txt")
        print()
        return False
    
    if missing_optional:
        print("[INFO] Optional Dependencies Missing:")
        for dep in missing_optional:
            print(f"   • {dep}")
        print("   (Some features may be limited)")
        print()
    
    return True

def initialize_transcription():
    """Initialize transcription system"""
    print(" Transcription System Setup")
    print("-" * 40)
    
    try:
        from transcription_config import setup_transcription_environment
        config = setup_transcription_environment()
        
        device, compute_type = config.get_device_config()
        print(f"Model: {config['model_size']}")
        print(f"Device: {device}")
        print(f"Compute: {compute_type}")
        print(f"Storage: {config['recordings_dir']}")
        
        # Check model availability
        from whisper_model_downloader import WhisperModelManager
        model_manager = WhisperModelManager()
        
        if model_manager.is_model_installed(config['model_size']):
            print(f"[OK] Model '{config['model_size']}' ready")
        else:
            print(f"[WARN] Model '{config['model_size']}' not downloaded")
            print("   First run will prompt for download")
        
        print("[OK] Transcription system initialized")
        return True
        
    except Exception as e:
        print(f"[ERROR] Transcription setup failed: {e}")
        return False

def run_application():
    """Run the main application"""
    print(" Starting Application")
    print("-" * 40)
    
    try:
        # Start health monitoring
        from transcription_health_monitor import get_health_monitor
        health_monitor = get_health_monitor()
        health_monitor.start_monitoring()
        print("[OK] Health monitoring started")
        
        # Import and run session recorder
        print("Loading session recorder...")
        
        # Create managers
        from config_manager import SecureConfigManager
        from audio_manager import AudioManager
        from enhanced_whisper_manager import EnhancedWhisperManager
        from session_recorder_window import SessionRecorderWindow
        
        config_manager = SecureConfigManager()
        audio_manager = AudioManager()
        
        # Initialize with enhanced whisper
        from transcription_config import get_transcription_config
        trans_config = get_transcription_config()
        whisper_manager = EnhancedWhisperManager(trans_config['model_size'])
        
        print("[OK] Managers initialized")
        
        # Create and run session recorder
        def on_insights_request(transcript, prompt, analysis_type):
            print(f"Analysis requested: {analysis_type}")
            if transcript:
                print(f"Transcript length: {len(transcript)} characters")
        
        recorder = SessionRecorderWindow(
            config_manager,
            audio_manager,
            whisper_manager,
            on_insights_request
        )
        
        print("[OK] Session recorder ready")
        print()
        print("SUCCESS: Application started successfully!")
        print("   Close the window to exit.")
        print()
        
        # Run the application
        recorder.run()
        
        # Cleanup
        health_monitor.stop_monitoring()
        print("[OK] Application closed cleanly")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Application failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point"""
    show_banner()
    
    # System check
    if not check_system():
        print("[ERROR] System check failed. Please address the issues above.")
        input("Press Enter to exit...")
        return 1
    
    print("[OK] System check passed")
    print()
    
    # Dependency check
    if not check_dependencies():
        print("[ERROR] Dependency check failed. Please install missing packages.")
        input("Press Enter to exit...")
        return 1
    
    print("[OK] All dependencies available")
    print()
    
    # Initialize transcription
    if not initialize_transcription():
        print("[ERROR] Transcription initialization failed.")
        print("   The application may still work with limited functionality.")
        print()
        response = input("Continue anyway? (y/N): ").lower()
        if response != 'y':
            return 1
    
    print()
    
    # Run application
    print("Ready to start!")
    input("Press Enter to launch Amanuensis Enhanced...")
    print()
    
    success = run_application()
    
    if not success:
        print()
        print("[ERROR] Application encountered errors.")
        print("   Check the output above for details.")
        input("Press Enter to exit...")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[WARN] Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
