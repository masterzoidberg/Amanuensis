#!/usr/bin/env python3
"""
Integration Demo
Demonstrates the complete transcription system end-to-end
"""

import os
import sys
import time
import threading
import numpy as np
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

def run_integration_demo():
    """Run complete integration demonstration"""
    print("🚀 Amanuensis Transcription System Integration Demo")
    print("=" * 60)
    
    try:
        # Step 1: Setup Environment
        print("\n📋 Step 1: Setting up environment...")
        from transcription_config import setup_transcription_environment
        config = setup_transcription_environment()
        print(f"✅ Environment configured")
        print(f"   Model: {config['model_size']}")
        print(f"   Device: {config.get_device_config()[0]}")
        print(f"   Storage: {config['recordings_dir']}")
        
        # Step 2: Initialize Health Monitoring
        print("\n🏥 Step 2: Starting health monitoring...")
        from transcription_health_monitor import get_health_monitor, update_model_status
        health_monitor = get_health_monitor()
        health_monitor.start_monitoring()
        print("✅ Health monitoring active")
        
        # Step 3: Initialize Components
        print("\n🔧 Step 3: Initializing components...")
        
        # Storage Manager
        from session_storage_manager import SessionStorageManager
        storage_manager = SessionStorageManager()
        print("✅ Storage manager initialized")
        
        # Enhanced Whisper Manager
        from enhanced_whisper_manager import EnhancedWhisperManager
        whisper_manager = EnhancedWhisperManager(config['model_size'])
        print("✅ Whisper manager initialized")
        
        # Step 4: Check System Status
        print("\n📊 Step 4: System status check...")
        model_status = whisper_manager.get_model_status()
        health_status = health_monitor.get_health_summary()
        
        print(f"   Model Status: {'Loaded' if model_status['loaded'] else 'Not Loaded'}")
        print(f"   Health Status: {health_status['overall_status']}")
        print(f"   Available: {model_status['available']}")
        
        # Step 5: Attempt Model Loading
        print("\n📥 Step 5: Model loading...")
        try:
            if whisper_manager.load_model():
                print("✅ Model loaded successfully")
                model_loaded = True
            else:
                print("⚠️ Model not loaded (may not be downloaded)")
                model_loaded = False
        except Exception as e:
            print(f"⚠️ Model loading failed: {e}")
            model_loaded = False
        
        # Step 6: Start Session
        print("\n💾 Step 6: Starting session...")
        session_metadata = {
            'demo': True,
            'timestamp': time.time(),
            'model': config['model_size'],
            'device': config.get_device_config()[0]
        }
        session_id = storage_manager.start_session(session_metadata)
        print(f"✅ Session started: {session_id}")
        
        # Step 7: Simulate Transcription Activity
        print("\n🎤 Step 7: Simulating transcription activity...")
        
        # Create mock segments
        class MockSegment:
            def __init__(self, text, speaker, start_time, confidence=0.9):
                self.text = text
                self.speaker = speaker
                self.start_time = start_time
                self.end_time = start_time + len(text.split()) * 0.5  # ~0.5s per word
                self.confidence = confidence
                self.is_partial = False
        
        # Demo conversation
        demo_segments = [
            MockSegment("Hello, welcome to today's therapy session.", "Therapist", time.time()),
            MockSegment("Thank you, I'm glad to be here.", "Client", time.time() + 3),
            MockSegment("How are you feeling today?", "Therapist", time.time() + 6),
            MockSegment("I've been feeling a bit anxious lately.", "Client", time.time() + 9),
            MockSegment("Can you tell me more about what's causing that anxiety?", "Therapist", time.time() + 13),
            MockSegment("It's mainly work-related stress and some personal issues.", "Client", time.time() + 18),
            MockSegment("I understand. Let's explore those feelings together.", "Therapist", time.time() + 23),
        ]
        
        # Process segments
        for i, segment in enumerate(demo_segments):
            print(f"   Processing segment {i+1}/{len(demo_segments)}: {segment.text[:30]}...")
            
            # Save to storage
            success = storage_manager.save_transcript_segment(segment)
            if success:
                print(f"   ✅ Saved: [{segment.speaker}] {segment.text}")
            else:
                print(f"   ❌ Failed to save segment")
            
            # Update health metrics
            from transcription_health_monitor import increment_segments_processed, update_inference_latency
            increment_segments_processed()
            update_inference_latency(0.5)  # Mock processing time
            
            time.sleep(0.5)  # Simulate real-time processing
        
        # Step 8: Test Real Transcription (if model loaded)
        if model_loaded:
            print("\n🎯 Step 8: Testing real transcription...")
            try:
                # Create test audio
                sample_rate = 16000
                duration = 2  # 2 seconds
                test_audio = np.random.random(sample_rate * duration).astype(np.float32) * 0.05
                
                # Setup callback
                transcription_received = threading.Event()
                transcription_result = None
                
                def on_transcription(result):
                    nonlocal transcription_result
                    transcription_result = result
                    transcription_received.set()
                
                whisper_manager.add_result_callback(on_transcription)
                whisper_manager.start_processing()
                
                # Send test audio
                whisper_manager.transcribe_audio_chunk(test_audio, sample_rate)
                
                # Wait for result
                if transcription_received.wait(timeout=15):
                    print(f"✅ Real transcription: '{transcription_result.full_text}'")
                    print(f"   Processing time: {transcription_result.processing_time:.2f}s")
                    
                    # Save real transcription result
                    for segment in transcription_result.segments:
                        storage_manager.save_transcript_segment(segment)
                else:
                    print("⚠️ Transcription timeout")
                
                whisper_manager.stop_processing()
                
            except Exception as e:
                print(f"⚠️ Real transcription test failed: {e}")
        else:
            print("\n⏭️ Step 8: Skipping real transcription (model not loaded)")
        
        # Step 9: Session Summary
        print("\n📋 Step 9: Session summary...")
        session_info = storage_manager.get_session_info()
        if session_info:
            stats = session_info['stats']
            print(f"   Session ID: {session_info['session_id']}")
            print(f"   Total segments: {stats['total_segments']}")
            print(f"   Speakers: {list(stats['speakers'])}")
            print(f"   Duration: {stats['total_duration']:.1f}s")
        
        # Step 10: Health Check
        print("\n🏥 Step 10: Final health check...")
        final_health = health_monitor.get_health_summary()
        print(f"   Overall status: {final_health['overall_status']}")
        print(f"   Total segments processed: {final_health['metrics'].get('total_segments', {}).get('value', 0)}")
        print(f"   Error count: {len(final_health['recent_errors'])}")
        
        # Show some metrics
        for metric_name, metric_data in final_health['metrics'].items():
            if metric_data['value'] > 0:
                unit = metric_data.get('unit', '')
                print(f"   {metric_name}: {metric_data['value']:.2f}{unit}")
        
        # Step 11: Storage and Cleanup
        print("\n💾 Step 11: Finalizing session...")
        
        # End session
        final_session_info = storage_manager.end_session()
        if final_session_info:
            print(f"✅ Session saved with {final_session_info['stats']['total_segments']} segments")
            
            # Show storage paths
            paths = final_session_info['storage_paths']
            print(f"   Transcript file: {paths['transcript_txt']}")
            print(f"   JSONL file: {paths['transcript_jsonl']}")
            
            # Check if files exist
            if Path(paths['transcript_txt']).exists():
                file_size = Path(paths['transcript_txt']).stat().st_size
                print(f"   Transcript file size: {file_size} bytes")
        
        # Get storage stats
        storage_stats = storage_manager.get_storage_stats()
        print(f"   Total storage used: {storage_stats.get('total_size_mb', 0):.2f} MB")
        print(f"   Total sessions: {storage_stats.get('session_count', 0)}")
        
        # Stop health monitoring
        health_monitor.stop_monitoring()
        
        # Step 12: Demo Complete
        print("\n🎉 Step 12: Demo complete!")
        print("=" * 60)
        print("✅ Integration demo finished successfully")
        print("\nThe system demonstrated:")
        print("  • Configuration management")
        print("  • Health monitoring")
        print("  • Session storage")
        print("  • Transcript processing")
        print("  • Error handling")
        if model_loaded:
            print("  • Real model inference")
        print("  • File persistence")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_system_requirements():
    """Show system requirements and recommendations"""
    print("\n📋 System Requirements Check")
    print("=" * 40)
    
    # Check Python version
    import sys
    python_version = sys.version_info
    print(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version >= (3, 8):
        print("✅ Python version OK")
    else:
        print("❌ Python 3.8+ required")
    
    # Check dependencies
    dependencies = [
        ("numpy", "1.24.0+"),
        ("faster-whisper", "1.0.0+"),
        ("torch", "2.0.0+"),
        ("soundfile", "0.12.1+"),
        ("psutil", "5.9.0+"),
    ]
    
    print("\nDependency check:")
    for package, version in dependencies:
        try:
            __import__(package)
            print(f"✅ {package} available")
        except ImportError:
            print(f"❌ {package} missing (required: {version})")
    
    # Check system resources
    try:
        import psutil
        
        # Memory
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        print(f"\nSystem memory: {memory_gb:.1f} GB")
        if memory_gb >= 8:
            print("✅ Memory OK for most models")
        elif memory_gb >= 4:
            print("⚠️ Limited memory - use small models")
        else:
            print("❌ Insufficient memory")
        
        # Disk space
        disk = psutil.disk_usage('.')
        free_gb = disk.free / (1024**3)
        print(f"Free disk space: {free_gb:.1f} GB")
        if free_gb >= 10:
            print("✅ Disk space OK")
        else:
            print("⚠️ Limited disk space")
            
    except ImportError:
        print("⚠️ psutil not available - cannot check system resources")
    
    # Check CUDA availability
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"\n✅ CUDA GPU available: {gpu_name}")
            print("   Recommended for best performance")
        else:
            print("\n⚠️ No CUDA GPU detected")
            print("   CPU inference will be slower")
    except ImportError:
        print("\n⚠️ PyTorch not available - cannot check CUDA")

if __name__ == "__main__":
    print("🔍 Checking system requirements...")
    show_system_requirements()
    
    print("\n" + "="*60)
    input("Press Enter to start the integration demo...")
    
    success = run_integration_demo()
    
    if success:
        print("\n🎊 Demo completed successfully!")
        print("The transcription system is ready for use.")
    else:
        print("\n💥 Demo encountered issues.")
        print("Check the error messages above for troubleshooting.")
    
    sys.exit(0 if success else 1)
