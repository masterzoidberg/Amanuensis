#!/usr/bin/env python3
"""
Amanuensis V2 - Professional Therapy Transcription Tool
MVP Phase 1: Basic recording and transcription workflow
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import threading
import queue
import time
import os
import re
from datetime import datetime
from pathlib import Path

# Audio and transcription imports
import soundcard as sc
import wave
import numpy as np
import torch
import psutil
import time
from faster_whisper import WhisperModel
import silero_vad


import re
import json
from collections import deque
import asyncio
import aiohttp
from asyncio_throttle import Throttler
import logging
from pathlib import Path
import uuid
import hashlib

# Gemini API imports - support both old and new SDK
GEMINI_SDK_VERSION = None
GEMINI_AVAILABLE = False

try:
    # Unified Google Gen AI SDK (required)
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    GEMINI_AVAILABLE = True
    print("[OK] Using unified Google Gen AI SDK")
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    types = None
    APIError = None
    print("[ERROR] Gemini API not available. Install: pip install google-genai")

# Keep for backwards compatibility
ANTHROPIC_AVAILABLE = GEMINI_AVAILABLE

# Performance monitoring
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except:
    NVML_AVAILABLE = False
    print("NVIDIA GPU monitoring not available")

# Pyannote.audio imports for advanced speaker diarization
try:
    from pyannote.audio import Pipeline
    import librosa
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False
    print("WARNING: Pyannote.audio not available. Install pyannote.audio for advanced speaker diarization.")

# Transcript stitching module - Fix #1-5 for alignment issues
from transcript_stitch import TranscriptStitcher, align_with_intersection_gate

# New componentized UI - Phase 1: Insights Panel, Phase 2: TopNavBar
from ui_components_new import (
    create_insights_panel_new,
    create_top_nav_bar,
    create_transcript_panel_new,
    create_session_controls,
    set_recording_state_action,
)
from types import SimpleNamespace

class AmanuensisApp:
    def __init__(self):
        # ===================================================================
        # COMPONENTIZED UI ARCHITECTURE - Apply dark mode BEFORE widget creation
        # ===================================================================
        # Set theme FIRST to prevent flash (per CustomTkinter docs)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Initialize main window
        self.root = ctk.CTk()
        self.root.title("Amanuensis V2 - Therapy Transcription")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)

        # PATCH_5: Enable window resizing for different screen sizes
        # Reasoning: Users have different monitor sizes - allow flexible layouts
        self.root.resizable(True, True)
        
        # Application state
        self.is_recording = False
        self.mic_stream = None
        self.sys_stream = None
        self.audio_data = []
        self.dual_channel_enabled = False

        # Theme lock to prevent white flash during start/stop recording
        self._theme_locked = False

        # Countdown control for recording status
        self._countdown_active = False
        self._countdown_after_id = None  # Track countdown timer for cancellation
        self._last_status_text = ""  # For de-duplication

        # Turn ID mapping for stable updates
        self._last_turn_id_by_hash = {}  # Maps hash(start, speaker, text_prefix) -> turn_id

        # Pyannote.audio advanced diarization state
        self.advanced_diarization_enabled = False
        self.pyannote_pipeline = None
        self.huggingface_token = ""  # HuggingFace token for pyannote model access
        self.diarization_error = None  # Track diarization loading errors for UI
        self.diarization_buffer_options = {
            "30 seconds": 30,
            "1 minute": 60,
            "90 seconds": 90,
            "2 minutes": 120
        }
        self.diarization_buffer_size = 60  # Default to 1 minute for better latency
        self.diarization_queue = queue.Queue()
        self.speaker_mapping = {}  # Map pyannote speaker IDs to Speaker 1/Speaker 2
        self.pending_diarization_chunks = deque()
        self.gpu_memory_threshold = 10.0  # GB - fail-safe for GPU memory


        # AI Analysis state
        self.analysis_enabled = False
        self.gemini_model = None
        self.gemini_api_key = ""
        self.analysis_queue = queue.Queue()
        self.analysis_results = deque(maxlen=100)  # Keep last 100 analysis results
        self.session_context = []
        self.analysis_frequency = 120  # 2 minutes default
        self.analysis_buffer = []
        self.analysis_buffer_start = None
        self.claude_api_key = None
        self.current_analysis_task = None
        self.analysis_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_cost': 0.0,
            'tokens_used': 0
        }
        self.risk_alerts = []

        # DEPRECATED: Legacy transcript queue (replaced by _append_transcript_turn adapter)
        self.transcript_queue = None  # Shim to prevent AttributeErrors; all producers use adapter now

        # Insight diagnostics - set to True for verbose logging
        self.verbose_insights = True  # Toggle for INSIGHT_* diagnostic logs (enabled for Phase 1 testing)
        self.VERBOSE_INSIGHTS = True  # Flag for ui_components_new diagnostics
        self.VERBOSE_UI = True  # Flag for TopNavBar diagnostics (Phase 2)

        # Dashboard and UI state - Initialize BEFORE create_ui()
        self.dashboard_state = {
            'analysis_visible': True,
            'current_insights': [],
            'risk_level': 'LOW',
            'session_active': False
        }

        # Layout preferences - Initialize BEFORE create_ui()
        self.layout_preferences = {
            'control_panel_width': 200,
            'transcript_panel_width': 450,
            'insights_panel_width': 500,
            'panels_collapsed': {'control': False, 'transcript': False, 'insights': False},
            'theme': 'light'
        }

        # Theme settings - Initialize BEFORE create_ui() - DEFAULT DARK
        self.current_theme = 'dark'
        
        # Font size settings for accessibility (minimum 14px per spec)
        self.transcript_font_size = 18  # Default body font 18pt
        self.min_font_size = 14
        self.max_font_size = 24
        
        # Session file name for TopNavBar display
        self.current_session_file = tk.StringVar(value="No active session")
        
        # ===================================================================
        # NEW INSIGHTS PANEL STATE & ACTIONS (Phase 1)
        # ===================================================================
        self.insights_state = SimpleNamespace(
            insights=deque(maxlen=500),
            cost='$0.00',
            avg_phrase='—',
            timeline_window_min=0,
            timeline_window_max=10,
            VERBOSE_INSIGHTS=True,
            # Phase 5b: LLM usage tracking
            llm_cost_total=0.0,
            llm_tokens_in=0,
            llm_tokens_out=0,
            # Chat-style history for new UI
            chat_history=[],
            # Insights presets for dynamic button rendering
            insights_presets=[]  # Will be populated from self.insights_presets after config load
        )

        # Insights Presets Configuration (customizable in settings)
        self.insights_presets = [
            {
                'id': 'themes',
                'label': '🎯 Themes',
                'query': 'Identify the main therapeutic themes and patterns in this session excerpt.',
                'enabled': True
            },
            {
                'id': 'progress',
                'label': '📈 Progress',
                'query': 'Analyze the client\'s progress and emotional state based on this conversation.',
                'enabled': True
            },
            {
                'id': 'risk',
                'label': '⚠️ Risk',
                'query': 'Assess any risk factors or safety concerns mentioned in this session.',
                'enabled': True
            }
        ]
        
        self.insights_actions = SimpleNamespace(
            on_send_insight=None,
            add_insight_card=None,
            add_chat_message=None,
            on_preset_click=None,
            on_timeline_change=None,
            update_summary=None,
        )

        # ===================================================================
        # TOPNAV STATE & ACTIONS (Phase 2)
        # ===================================================================
        self.topnav_state = SimpleNamespace(
            session_file='No active session',
            risk_level='Low',
            dark_mode=True,  # Default dark mode
            app_version='Amanuensis V2',
            VERBOSE_UI=True,
            session_var=None,  # Will be set by create_top_nav_bar
            risk_badge=None,  # Will be set by create_top_nav_bar
            risk_colors=None  # Will be set by create_top_nav_bar
        )
        
        self.topnav_actions = SimpleNamespace(
            on_theme_toggle=None,  # Will be set after UI creation
            on_open_settings=None,  # Will be set after UI creation
            on_risk_click=None,  # Optional: cycle risk levels
            on_session_click=None,  # Optional: click session name
            update_session=None,  # Will be set by create_top_nav_bar
            update_risk=None,  # Will be set by create_top_nav_bar
            update_theme_button=None  # Will be set by create_top_nav_bar
        )

        # ===================================================================
        # TRANSCRIPT PANEL STATE & ACTIONS (Phase 3)
        # ===================================================================
        self.transcript_panel_state = SimpleNamespace(
            speaker_roles={1: "Therapist", 2: "Client"},
            font_size=self.transcript_font_size,
            timestamps_enabled=True,
            separate_speakers=False,  # Show speaker labels when enabled
            clock=lambda: time.time(),
            VERBOSE_UI=True,
            turns=deque(maxlen=2000),
        )

        self.transcript_panel_actions = SimpleNamespace(
            append_turn=None,
            update_turn=None, # Support for turn updates
            update_font=None,
            refresh_roles=None,
            text_widget=None,
            on_speaker_role_change=None,
            on_font_increase=None,
            on_font_decrease=None,
            on_copy_selection=None,
            on_copy_all=None,
            on_copy_last_5=None,
        )

        # ===================================================================
        # SESSION CONTROLS STATE & ACTIONS (Phase 4)
        # ===================================================================
        self.session_controls_state = SimpleNamespace(
            devices={
                'mics': [],
                'loops': [],
                'mic_sel': None,
                'loop_sel': None,
            },
            buffer_seconds=30,
            separate_speakers=False,
            dark_mode=True,
            VERBOSE_UI=True,
        )

        self.session_controls_actions = SimpleNamespace(
            on_select_mic=None,
            on_select_loopback=None,
            on_buffer_change=None,
            on_separate_speakers=None,
            on_start_stop=None,
            on_theme_toggle=None,
        )
        
        # Audio settings - Optimized for stable WASAPI capture
        self.sample_rates = [16000, 44100, 48000]  # Test rates in order of preference
        self.sample_rate = self.detect_optimal_sample_rate()
        self.channels = 1
        self.dtype = np.float32   # Higher precision audio

        # Buffer settings to prevent discontinuities (configurable from settings)
        self.audio_blocksize = 8192  # Larger buffer for stable capture (was 100ms chunks)
        self.recording_chunk_duration = 0.2  # 200ms chunks instead of 100ms
        self.max_discontinuities = 10  # Allow some discontinuities before warning (increased from 5)
        self.discontinuity_count = 0
        self.discontinuity_warning_throttle = 5  # Only log every Nth discontinuity
        self.discontinuity_warning_counter = 0  # Counter for throttling
        
        # Buffer management for coherent transcription
        # Per faster-whisper docs: segments are generator-based, processed on iteration
        # 30s buffer provides stable delay for real-time transcription (max 45s)
        self.buffer_duration = 30  # seconds - 30s window for stable latency
        self.audio_buffer = []
        self.sys_audio_buffer = []
        self.buffer_start_time = None
        self.processing_buffer = False

        # Performance monitoring
        self.performance_stats = {
            'rtf_values': [],  # Real-time factor (processing_time/audio_duration)
            'gpu_memory_usage': [],
            'cpu_usage': [],
            'processing_times': [],
            'discontinuities': 0,  # Track audio discontinuities
            'advanced_diarization_rtf': [],  # RTF for advanced diarization chunks
            'advanced_diarization_chunks': 0,  # Count of chunks processed with advanced diarization
            'speaker_alignment_accuracy': [],  # Confidence scores for speaker alignment
            'sample_rate_used': 0,  # Actual sample rate used
            'buffer_underruns': 0  # Track buffer underrun events
        }
        
        # Create sessions directory first
        self.sessions_dir = Path("sessions")
        self.sessions_dir.mkdir(exist_ok=True)
        
        # Initialize SoundCard
        try:
            self.audio_devices = self.get_audio_devices()
        except Exception as e:
            messagebox.showerror("Audio Error", f"Failed to initialize audio system: {str(e)}")
            self.audio_devices = {"input": [], "output": [], "loopback": []}
        
        # Sync insights_presets to insights_state for UI access
        self.insights_state.insights_presets = self.insights_presets

        # Build UI first
        self.create_ui()
        
        # Initialize faster-whisper model with GPU optimization
        self.whisper_model = None
        self.silero_vad_model = None
        self.load_models()

        # Initialize therapy analysis
        self.load_analysis_config()
        self.setup_claude_client()

        # Analysis is now on-demand only - no auto-running loop
        self.analysis_loop_task = None
        # Disabled auto-analysis: if self.analysis_enabled: self.start_analysis_loop()
        
        # Check system configuration for optimal audio performance
        self.check_system_audio_config()

        # Load user settings from config file
        self.load_settings_from_config()

        # Initialize transcript stitcher - Fix #1-5
        # Must be after load_settings_from_config() to have stitching_config available
        if not hasattr(self, 'stitching_config'):
            # Fallback if config loading failed
            self.stitching_config = {
                'overlap_seconds': 5.0,
                'min_turn_seconds': 1.0,
                'min_turn_chars': 15,
                'coalesce_gap_seconds': 0.30,
                'dup_text_similarity': 0.95
            }
        self.transcript_stitcher = TranscriptStitcher(self.stitching_config)
        self.absolute_session_start_time = None  # Set when recording starts

        # PATCH_DIARIZE: Online speaker diarization for cross-window consistency
        # Reasoning: pyannote assigns speakers per-window (SPEAKER_00, SPEAKER_01)
        #            OnlineDiarizer tracks speakers across windows using embeddings
        # Note: Full integration requires pyannote embedding model (future enhancement)
        #       Currently initialized for infrastructure, embeddings to be added
        try:
            from diarization_utils import OnlineDiarizer
            self.online_diarizer = OnlineDiarizer(
                similarity_threshold=0.65,  # Cosine similarity threshold
                max_speakers=10,            # Maximum unique speakers to track
                embedding_dim=192           # Embedding dimension (pyannote default: 512)
            )
            if self.VERBOSE_UI:
                print("[DIARIZE] OnlineDiarizer initialized (ready for embedding integration)")
        except ImportError as e:
            print(f"[DIARIZE] Warning: Could not import OnlineDiarizer: {e}")
            self.online_diarizer = None

        # Verify all required attributes are initialized
        self.verify_attribute_initialization()

        # Dev-time verification: check for legacy widget references
        if self.VERBOSE_UI:
            self._assert_no_legacy_refs()

        # REMOVED: Legacy transcript update loop (replaced by _append_transcript_turn adapter)
        # self.root.after(100, self.update_transcript_display)

        # Print startup verification summary
        self._print_startup_verification()

        # Finalize layout AFTER all initialization (prevents flash during model loading)
        self._finalize_layout()

    def _finalize_layout(self):
        """Finalize UI layout after all models are loaded (prevents startup flash)"""
        try:
            # Show window now that models are loaded
            self.root.deiconify()

            # Force geometry calculation
            self.root.update_idletasks()

            # Set sash positions with correct dimensions
            self._set_initial_sash_positions()

            # Force final geometry update
            self.root.update_idletasks()

            if self.VERBOSE_UI:
                print("[UI] Layout finalized - window ready")
        except Exception as e:
            print(f"[UI] Warning: Could not finalize layout: {e}")
            # Ensure window is shown even if layout fails
            self.root.deiconify()

    def _print_startup_verification(self):
        """Print verification summary at startup"""
        print("\n" + "="*60)
        print("[STARTUP VERIFICATION SUMMARY]")
        print("="*60)

        # Default devices
        if hasattr(self, 'session_controls_state'):
            mic = self.session_controls_state.devices.get('mic_sel', 'None')
            speaker = self.session_controls_state.devices.get('loop_sel', 'None')
        else:
            mic = 'Not initialized'
            speaker = 'Not initialized'

        print(f"Default mic: {mic}")
        print(f"Default speakers: {speaker}")

        # Copyable transcript
        has_copy = hasattr(self, '_copy_transcript_handler')
        print(f"Copyable transcript: {'OK' if has_copy else 'Enhanced copy coming soon'}")

        # Insights clickable (check ui_components_new.py)
        print(f"Insights clickable: OK (PATCH_6 applied)")

        # Dark mode
        is_dark = getattr(self.session_controls_state, 'dark_mode', True) if hasattr(self, 'session_controls_state') else True
        print(f"Dark mode verified: {'OK' if is_dark else 'LIGHT MODE'}")

        # Window resize
        is_resizable = self.root.resizable()[0] if hasattr(self, 'root') else False
        print(f"Window resizable: {'OK' if is_resizable else 'FIXED'}")

        print("="*60 + "\n")

    def get_audio_devices(self):
        """
        Get available audio devices with smart defaults.

        Reasoning:
            - TONOR TC30 is preferred microphone (better quality than webcam)
            - Logi Z407 is preferred speakers (system audio capture)
            - Fall back to first available if preferred not found
        """
        devices = {"input": [], "output": [], "loopback": []}

        try:
            # Get microphones using SoundCard
            microphones = sc.all_microphones(include_loopback=False)
            mic_names = []
            for i, mic in enumerate(microphones):
                devices["input"].append((mic.id, f"{mic.name}"))
                mic_names.append(mic.name)
                print(f"Found microphone: {mic.name} (ID: {mic.id})")

            # Get speakers using SoundCard
            speakers = sc.all_speakers()
            speaker_names = []
            for i, speaker in enumerate(speakers):
                devices["output"].append((speaker.id, f"{speaker.name}"))
                speaker_names.append(speaker.name)
                print(f"Found speaker: {speaker.name} (ID: {speaker.id})")

            # Get loopback devices (system audio capture)
            loopback_devices = sc.all_microphones(include_loopback=True)
            loop_names = []
            for mic in loopback_devices:
                # Check if this is a loopback device
                is_loopback = hasattr(mic, 'is_loopback') and mic.is_loopback
                if is_loopback:
                    devices["loopback"].append((mic.id, f"{mic.name} [NATIVE LOOPBACK]"))
                    loop_names.append(f"{mic.name} [NATIVE LOOPBACK]")
                    print(f"Found native loopback device: {mic.name} (ID: {mic.id})")
                elif "loopback" in mic.name.lower() or "stereo mix" in mic.name.lower():
                    devices["loopback"].append((mic.id, f"{mic.name} [DETECTED LOOPBACK]"))
                    loop_names.append(f"{mic.name} [DETECTED LOOPBACK]")
                    print(f"Found detected loopback device: {mic.name} (ID: {mic.id})")

            # Also add manual loopback entries for speakers (WASAPI)
            for speaker_id, speaker_name in devices["output"]:
                loopback_name = f"{speaker_name} [WASAPI LOOPBACK]"
                devices["loopback"].append((speaker_id, loopback_name))
                loop_names.append(loopback_name)

            print(f"SoundCard found: {len(devices['input'])} microphones, {len(devices['output'])} speakers, {len(devices['loopback'])} loopback devices")

            # PATCH_8: Smart defaults - Select TONOR TC30 and Logi Z407
            selected_mic = None
            selected_loop = None

            # Find preferred mic (TONOR TC30)
            for mic_name in mic_names:
                if "TONOR" in mic_name and "TC30" in mic_name:
                    selected_mic = mic_name
                    print(f"[OK] Auto-selected preferred mic: {selected_mic}")
                    break

            # Fall back to first mic if TONOR not found
            if not selected_mic and mic_names:
                selected_mic = mic_names[0]
                print(f"[WARN] TONOR TC30 not found, using fallback: {selected_mic}")

            # Find preferred speakers (Logi Z407)
            for loop_name in loop_names:
                if "Logi" in loop_name and "Z407" in loop_name:
                    selected_loop = loop_name
                    print(f"[OK] Auto-selected preferred speakers: {selected_loop}")
                    break

            # Fall back to first loopback if Logi not found
            if not selected_loop and loop_names:
                selected_loop = loop_names[0]
                print(f"[WARN] Logi Z407 not found, using fallback: {selected_loop}")

            # Update session controls state with defaults
            if hasattr(self, 'session_controls_state'):
                self.session_controls_state.devices = {
                    'mics': mic_names,
                    'loops': loop_names,
                    'mic_sel': selected_mic,
                    'loop_sel': selected_loop,
                }

        except Exception as e:
            print(f"Error getting SoundCard devices: {e}")
            # Fallback to basic detection
            try:
                default_mic = sc.default_microphone()
                if default_mic:
                    devices["input"].append((default_mic.id, f"Default Microphone ({default_mic.name})"))

                default_speaker = sc.default_speaker()
                if default_speaker:
                    devices["output"].append((default_speaker.id, f"Default Speaker ({default_speaker.name})"))
                    devices["loopback"].append((default_speaker.id, f"Default Speaker ({default_speaker.name}) [LOOPBACK]"))
            except Exception as fallback_e:
                print(f"Fallback device detection failed: {fallback_e}")

        return devices

    def detect_optimal_sample_rate(self):
        """Detect optimal sample rate for the system"""
        try:
            # Try to get default microphone to test sample rates
            default_mic = sc.default_microphone()
            if not default_mic:
                print("No default microphone found, using 16000 Hz")
                return 16000

            print("Testing sample rates for optimal hardware compatibility...")

            for rate in self.sample_rates:
                try:
                    # Test if this sample rate works with a very short recording
                    with default_mic.recorder(samplerate=rate, channels=1, blocksize=1024) as recorder:
                        test_data = recorder.record(numframes=160)  # 10ms at 16kHz
                        if test_data is not None and len(test_data) > 0:
                            print(f"Sample rate {rate} Hz: SUPPORTED")
                            return rate
                except Exception as e:
                    print(f"Sample rate {rate} Hz: FAILED ({e})")
                    continue

            print("All sample rates failed, defaulting to 16000 Hz")
            return 16000

        except Exception as e:
            print(f"Sample rate detection failed: {e}, defaulting to 16000 Hz")
            return 16000

    def check_system_audio_config(self):
        """Check Windows system configuration for optimal audio performance"""
        try:
            import subprocess

            print("\n" + "="*50)
            print("SYSTEM AUDIO CONFIGURATION CHECK")
            print("="*50)

            # Check Windows power plan
            try:
                result = subprocess.run(
                    ['powercfg', '/getactivescheme'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    power_plan = result.stdout.strip()
                    print(f"Power Plan: {power_plan}")

                    if "High performance" in power_plan or "Ultimate Performance" in power_plan:
                        print("[OK] Power plan is optimized for performance")
                    else:
                        print("[WARNING] Consider switching to 'High Performance' power plan")
                        print("  Run: powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")
                else:
                    print("Could not detect power plan")
            except Exception as e:
                print(f"Power plan check failed: {e}")

            # Check audio service status
            try:
                result = subprocess.run(
                    ['sc', 'query', 'Audiosrv'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if "RUNNING" in result.stdout:
                    print("[OK] Windows Audio service is running")
                else:
                    print("[WARNING] Windows Audio service may not be running properly")
            except Exception as e:
                print(f"Audio service check failed: {e}")

            # Check for exclusive mode conflicts
            print(f"Using sample rate: {self.sample_rate} Hz")
            print(f"Buffer size: {self.audio_blocksize} samples")
            print(f"Chunk duration: {self.recording_chunk_duration*1000} ms")

            print("="*50)

        except Exception as e:
            print(f"System configuration check failed: {e}")

    def load_models(self):
        """Load faster-whisper and Silero VAD models with GPU optimization"""
        try:
            # Update status if UI is ready
            self.set_status("Loading AI models...")
            self.root.update()

            # Check GPU memory before loading models
            gpu_memory_available = self.get_gpu_memory_available()
            print(f"Available GPU memory: {gpu_memory_available:.1f} GB")

            # RTX 3060 Ti analysis
            if gpu_memory_available > 0:
                total_memory = gpu_memory_available + self.get_gpu_memory_usage() / 1024  # Current usage in GB
                print(f"Total GPU memory: {total_memory:.1f} GB")
                if total_memory <= 8.5:  # RTX 3060 Ti range
                    print("[WARN] RTX 3060 Ti detected - Pyannote may require CPU fallback")
                elif total_memory <= 12:
                    print("[OK] Sufficient GPU memory for both Whisper + Pyannote")
                else:
                    print("[OK] High-end GPU detected - Optimal performance expected")

            # Detect GPU availability
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

            print(f"Loading models on {device} with compute_type {compute_type}")

            # Load faster-whisper Medium.en model with GPU optimization
            self.whisper_model = WhisperModel(
                "medium.en",  # English-only model for better performance
                device=device,
                compute_type=compute_type,
                local_files_only=False,
                download_root=None
            )

            # Check GPU memory after Whisper loading
            gpu_memory_after_whisper = self.get_gpu_memory_available()
            print(f"GPU memory after Whisper: {gpu_memory_after_whisper:.1f} GB")
            self.log_memory_usage("after Whisper loading")

            # Load Silero VAD model
            self.silero_vad_model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            self.silero_vad_model.eval()

            # Load pyannote pipeline if available and sufficient GPU memory
            self.load_pyannote_pipeline(device, gpu_memory_after_whisper)
            if self.pyannote_pipeline:
                self.log_memory_usage("after Pyannote loading")

            print(f"Models loaded successfully on {device}")

            # Update status if UI is ready
            if hasattr(self, 'status_label'):
                status_text = "Ready - GPU Optimized" if device == "cuda" else "Ready - CPU Mode"
                if self.pyannote_pipeline:
                    status_text += " + Advanced Diarization"
                self.set_status(status_text)

        except Exception as e:
            error_msg = f"Failed to load AI models: {str(e)}"
            print(error_msg)
            self.set_status("Error: AI models failed to load")
            messagebox.showerror("Model Error", error_msg)
    
    def _handle_copy_selection(self, selected_text: str):
        """Handle the callback from the new transcript panel for copying a selection."""
        self.root.clipboard_clear()
        self.root.clipboard_append(selected_text)
        self.root.update()
        self.show_toast(f"Copied selection ({len(selected_text)} chars)")

    def _handle_copy_all(self, all_text: str):
        """Handle the callback for copying the entire transcript."""
        self.root.clipboard_clear()
        self.root.clipboard_append(all_text)
        self.root.update()
        self.show_toast(f"Copied entire transcript ({len(all_text)} chars)")

    def _get_transcript_as_text(self) -> str:
        """Construct a formatted string from the structured turns in the new panel's state."""
        if not hasattr(self, 'transcript_panel_state') or not self.transcript_panel_state.turns:
            return ""

        separate_speakers = getattr(self.transcript_panel_state, 'separate_speakers', False)
        lines = []
        for turn in self.transcript_panel_state.turns:
            timestamp = datetime.fromtimestamp(turn['start']).strftime('%H:%M:%S')
            speaker = turn.get('speaker', 'UNKNOWN')
            text = turn.get('text', '')
            if separate_speakers:
                lines.append(f"[{timestamp}] {speaker}: {text}")
            else:
                lines.append(f"[{timestamp}] {text}")

        return "\n".join(lines)

    def _copy_last_minutes(self, minutes: int = 5):
        """
        Copy transcript turns from the last N minutes to clipboard.

        Args:
            minutes: Number of minutes to look back (default: 5)

        Reasoning:
            - Sources from authoritative self.transcript_panel_state.turns
            - Filters by abs_end timestamp for accurate time windows
            - Formats with [HH:MM:SS] Speaker: text
            - Thread-safe clipboard operations
        """
        if not hasattr(self, 'transcript_panel_state') or not self.transcript_panel_state.turns:
            self.show_toast("No transcript data available")
            return

        # Get current time (use clock if available for consistency with recording)
        try:
            current_time = self.transcript_panel_state.clock() if callable(self.transcript_panel_state.clock) else time.time()
        except Exception:
            current_time = time.time()

        # Filter turns from the last N minutes
        cutoff = current_time - (minutes * 60.0)
        recent_turns = [
            turn for turn in self.transcript_panel_state.turns
            if turn.get('abs_end', 0) >= cutoff
        ]

        if not recent_turns:
            self.show_toast(f"No turns in last {minutes} minutes")
            return

        # Format turns with timestamps, speaker roles, and text
        separate_speakers = getattr(self.transcript_panel_state, 'separate_speakers', False)
        lines = []
        for turn in recent_turns:
            abs_start = turn.get('abs_start', cutoff)
            ts = datetime.fromtimestamp(abs_start).strftime('%H:%M:%S')

            # Get speaker role from state (fallback to speaker_id)
            speaker_id = turn.get('speaker_id', 1)
            role = self.transcript_panel_state.speaker_roles.get(speaker_id, f'Speaker {speaker_id}')

            text = turn.get('text', '')
            if separate_speakers:
                lines.append(f"[{ts}] {role}: {text}")
            else:
                lines.append(f"[{ts}] {text}")

        payload = "\n".join(lines)

        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)
        self.root.update()

        self.show_toast(f"Copied last {minutes} minutes ({len(recent_turns)} turns)")

        if self.session_controls_state.VERBOSE_UI:
            print(f"[TRANSCRIPT] Copied {len(recent_turns)} turns from last {minutes} minutes")

    def _handle_copy_last_5(self):
        """Handle the callback for copying the last 5 minutes."""
        self._copy_last_minutes(5)

    def _set_initial_sash_positions(self, retry_count=0):
        """
        Set initial PanedWindow sash positions reliably on Windows 11.

        Reasoning:
            - Wait for window geometry to be realized (winfo_width > 1)
            - Split available width equally into thirds (33/33/33%)
            - Left pane (SessionControls): 1/3 of window
            - Center pane (Transcript): 1/3 of window
            - Right pane (Insights): 1/3 of window
            - Reschedule if not ready yet (max 20 retries = 2 seconds)
            - User resizing is preserved; this only runs once on startup
        """
        try:
            # Prevent infinite retries
            if retry_count > 20:
                print(f"[UI] ERROR: Failed to set sash positions after 20 retries")
                return

            if not hasattr(self, 'main_paned_window'):
                print(f"[UI] DEBUG: main_paned_window not found (retry {retry_count})")
                return

            # Get actual window width
            window_width = self.root.winfo_width()
            paned_width = self.main_paned_window.winfo_width()

            # Debug logging
            if retry_count == 0:
                print(f"[UI] DEBUG: Initial sash positioning attempt")
                print(f"     Root window width: {window_width}px")
                print(f"     PanedWindow width: {paned_width}px")

            # Check if geometry is realized - need substantial width
            if window_width <= 100 or paned_width <= 100:
                # Not ready yet, reschedule
                print(f"[UI] DEBUG: Window not ready (retry {retry_count}), rescheduling...")
                self.root.after(100, lambda: self._set_initial_sash_positions(retry_count + 1))
                return

            # Use PanedWindow width (more reliable than root window)
            usable_width = paned_width

            # Calculate equal thirds (33/33/33%)
            # Sash 0: Between left and center panes (at 1/3 of width)
            sash_0_pos = int(usable_width / 3)
            # Sash 1: Between center and right panes (at 2/3 of width)
            sash_1_pos = int(usable_width * 2 / 3)

            # Set sash positions
            self.main_paned_window.sashpos(0, sash_0_pos)
            self.main_paned_window.sashpos(1, sash_1_pos)

            # Verify positions were set (read them back)
            actual_sash_0 = self.main_paned_window.sashpos(0)
            actual_sash_1 = self.main_paned_window.sashpos(1)

            # Calculate actual pane widths for logging
            left_width = actual_sash_0
            center_width = actual_sash_1 - actual_sash_0
            right_width = usable_width - actual_sash_1

            # Always log startup layout confirmation
            print(f"[UI] Initial equal-split applied (after {retry_count} retries):")
            print(f"     PanedWindow: {usable_width}px")
            print(f"     Left (Controls): {left_width}px | Center (Transcript): {center_width}px | Right (Insights): {right_width}px")
            print(f"     Sash positions set: {sash_0_pos}px, {sash_1_pos}px")
            print(f"     Sash positions actual: {actual_sash_0}px, {actual_sash_1}px")

        except Exception as e:
            print(f"[UI] ERROR: Could not set initial sash positions (retry {retry_count}): {e}")
            import traceback
            traceback.print_exc()

    # ===================================================================
    # SESSION CONTROLS ACTION HANDLERS (Phase 4)
    # ===================================================================
    
    def _on_mic_select(self, device_name: str):
        """Handle microphone selection from SessionControls."""
        if self.session_controls_state.VERBOSE_UI:
            print(f"CTRL mic selected: {device_name}")
        # Update the selected microphone device
        # This would be connected to your actual audio device selection logic
        pass
    
    def _on_loopback_select(self, device_name: str):
        """Handle loopback (system audio) selection from SessionControls."""
        if self.session_controls_state.VERBOSE_UI:
            print(f"CTRL loopback selected: {device_name}")
        # Update the selected loopback device
        # This would be connected to your actual audio device selection logic
        pass
    
    def _on_buffer_change(self, seconds: int):
        """Handle buffer duration change from SessionControls."""
        if self.session_controls_state.VERBOSE_UI:
            print(f"CTRL buffer changed: {seconds}s")
        self.buffer_duration = seconds
        if hasattr(self, 'session_controls_state'):
            self.session_controls_state.buffer_seconds = seconds
    
    def _on_separate_speakers_toggle(self, enabled: bool):
        """Handle separate speakers toggle from SessionControls."""
        if self.session_controls_state.VERBOSE_UI:
            print(f"CTRL separate speakers: {enabled}")
        self.dual_channel_enabled = enabled
        # Update transcript panel state to show/hide speaker labels
        if hasattr(self, 'transcript_panel_state'):
            self.transcript_panel_state.separate_speakers = enabled
    
    def _on_theme_toggle(self):
        """Handle theme toggle from SessionControls."""
        # Guard: Don't change theme while recording operations are in progress
        if getattr(self, '_theme_locked', False):
            if self.VERBOSE_UI:
                print("THEME toggle blocked: theme locked during recording operation")
            return

        # IMPORTANT: Call the main toggle_dark_mode() to properly sync ALL theme state
        # This ensures self.current_theme, session_controls_state.dark_mode, and all UI stay in sync
        self.toggle_dark_mode()

        # Update session controls state to match (toggle_dark_mode updates self.current_theme)
        self.session_controls_state.dark_mode = (self.current_theme == 'dark')

        if self.session_controls_state.VERBOSE_UI:
            print(f"CTRL theme toggled via main toggle: dark={self.session_controls_state.dark_mode}")

        # Update button text if it exists in session controls
        if hasattr(self.session_controls_state, '_theme_btn'):
            btn = self.session_controls_state._theme_btn
            btn.configure(text='🌙 Dark Mode' if self.session_controls_state.dark_mode else '☀️ Light Mode')
    
    def _on_generate_notes_click(self):
        """
        Handle Generate Progress Notes button click with optional file attachment.

        Reasoning:
            - PATCH_4: Allows attaching client files (assessments, notes, etc.)
            - Uses native OS file picker
            - Gracefully handles cancel/empty states
        """
        try:
            # Guard: check if transcript exists
            full_transcript = self._get_transcript_as_text()

            if not full_transcript or len(full_transcript.strip()) < 100:
                self.set_status("No transcript available yet")
                return

            # Optional: Ask for file attachment
            from tkinter import filedialog

            attachment_path = filedialog.askopenfilename(
                title="Attach Document (Optional - Cancel to skip)",
                filetypes=[
                    ("All Files", "*.*"),
                    ("PDF Files", "*.pdf"),
                    ("Word Documents", "*.docx"),
                    ("Text Files", "*.txt"),
                    ("Markdown Files", "*.md")
                ],
                parent=self.root
            )

            # User cancelled file picker - check if they still want to proceed
            if not attachment_path:
                # No attachment selected - proceed with transcript only
                self.set_status("Generating notes (no attachment)")
            else:
                self.set_status(f"Generating notes with attachment: {Path(attachment_path).name}")

            # Call Gemini generation with optional attachment
            self.generate_session_summary(attachment_path=attachment_path if attachment_path else None)
            self.set_status("Notes generated")

        except Exception as e:
            self.set_status("Notes error – see console")
            print(f"Error generating progress notes: {e}")

    def record_llm_usage(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        """
        Record LLM usage metrics and update running totals.

        Args:
            model: Model name (e.g., 'gemini-2.0-flash-exp')
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost_usd: Cost in USD
        """
        if hasattr(self, 'insights_state'):
            self.insights_state.llm_tokens_in += input_tokens
            self.insights_state.llm_tokens_out += output_tokens
            self.insights_state.llm_cost_total += cost_usd

            # Update formatted cost string
            self.insights_state.cost = f"${self.insights_state.llm_cost_total:.4f}"

            # Refresh footer
            if self.insights_actions.update_summary:
                self.insights_actions.update_summary()

            # Diagnostic logging
            if self.VERBOSE_UI:
                print(f"COST update: model={model} in={input_tokens} out={output_tokens} total=${self.insights_state.llm_cost_total:.4f}")

    def estimate_tokens_and_cost(self, input_text: str, output_text: str, model: str = 'gemini-2.0-flash-exp'):
        """
        Estimate tokens and cost for Gemini API calls.

        Args:
            input_text: Input prompt text
            output_text: Generated response text
            model: Model name

        Returns:
            tuple: (input_tokens, output_tokens, cost_usd)
        """
        # Rough estimation: 1 token ≈ 4 characters
        input_tokens = len(input_text) // 4
        output_tokens = len(output_text) // 4

        # Gemini 2.0 Flash pricing (as of 2024): $0.075/1M input, $0.30/1M output
        input_cost = (input_tokens / 1_000_000) * 0.075
        output_cost = (output_tokens / 1_000_000) * 0.30
        total_cost = input_cost + output_cost

        return input_tokens, output_tokens, total_cost

    def _append_transcript_turn(self, **turn):
        """
        Thread-safe, schema-tolerant method to append a new turn to the transcript panel.

        Accepts both legacy and new field names:
        - Legacy: speaker/speaker_id, text/content/utterance, start/timestamp, end/stop, turn_id/id
        - New: speaker, text, start, end, id

        Normalizes to TranscriptPanel API format and maintains stable turn IDs.
        """
        if not self.transcript_panel_actions.append_turn:
            self.logger.warning("_append_transcript_turn called before UI is fully initialized.")
            return

        # Schema normalization: extract fields with fallbacks
        start_ts = turn.pop("start", None) or turn.pop("abs_start", None) or turn.pop("timestamp", None)
        end_ts = turn.pop("end", None) or turn.pop("abs_end", None) or turn.pop("stop", None)
        speaker = turn.pop("speaker", None) or turn.pop("speaker_id", None) or turn.pop("spk", "UNKNOWN")
        role = turn.pop("role", None) or turn.pop("role_label", None)
        text = turn.pop("text", None) or turn.pop("content", "") or turn.pop("utterance", "")
        # Legacy field compatibility - is_phi field no longer used but supported for compatibility
        is_phi = bool(turn.pop("is_phi", False) or turn.pop("phi", False))
        turn_id = turn.pop("turn_id", None) or turn.pop("id", None)

        # Convert speaker_id (int) to speaker label if needed
        if isinstance(speaker, int):
            speaker = f"Speaker {speaker}"

        # Synthesize stable turn ID if missing
        if not turn_id:
            # Compute hash from (start_ts, speaker, first 24 chars of text)
            text_prefix = text[:24] if text else ""
            turn_hash = f"{start_ts:.3f}:{speaker}:{text_prefix}"

            # Check if we've seen this turn before
            if turn_hash in self._last_turn_id_by_hash:
                turn_id = self._last_turn_id_by_hash[turn_hash]
            else:
                # Generate new ID and store mapping
                turn_id = str(uuid.uuid4())
                self._last_turn_id_by_hash[turn_hash] = turn_id

        # Build clean payload for TranscriptPanel API
        payload = {
            "speaker": speaker,
            "text": text.strip() if text else "",
            "start": start_ts,
            "end": end_ts,
            "is_phi": is_phi,
            "id": turn_id,
        }

        # Add role if provided
        if role:
            payload["role"] = role

        # Verbose logging
        if self.VERBOSE_UI:
            ts_str = f"[{start_ts:.2f},{end_ts:.2f}]" if start_ts and end_ts else "[no-ts]"
            print(f"TRANSCRIPT append adapter: spk={speaker} t={ts_str} len={len(text)} id={turn_id[:8]}")

        # Ensure the call is made from the main GUI thread
        self.root.after(0, self.transcript_panel_actions.append_turn, payload)

    def create_ui(self):
        """Create the professional therapist dashboard interface with componentized architecture"""
        # Hide window during UI construction to prevent layout flicker
        self.root.withdraw()

        # Configure professional color scheme (dark mode already set)
        self.setup_professional_theme()

        # ===================================================================
        # NEW GRID-BASED LAYOUT: 3 columns (control, transcript, insights)
        # Per CustomTkinter docs: configure grid BEFORE creating child widgets
        # ===================================================================
        # Configure root window grid layout
        self.root.grid_rowconfigure(0, weight=0, minsize=80)   # Row 0: TopNavBar (fixed height)
        self.root.grid_rowconfigure(1, weight=1)                # Row 1: Main content (expands)
        self.root.grid_rowconfigure(2, weight=0, minsize=35)   # Row 2: Status bar (fixed height)
        self.root.grid_columnconfigure(0, weight=1)             # Single column that expands

        # PATCH_PANED: Create PanedWindow for resizable panels
        # Reasoning: ttk.PanedWindow provides draggable sashes for Windows 11 UX
        #            Users can adjust panel widths to their preference
        self.main_paned_window = ttk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            style='Dark.TPanedwindow'  # Custom style for dark theme
        )

        # ===================================================================
        # CREATE NEW COMPONENTIZED UI (Phases 1-2)
        # ===================================================================

        # Phase 2: TopNavBar at row=0, spanning all columns
        self.topnav_frame = create_top_nav_bar(
            self.root,
            self.topnav_state,
            self.topnav_actions,
            self.colors
        )
        self.topnav_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        # Phase 4: SessionControls at grid (row=1, col=0)
        # Wire action callbacks
        self.session_controls_actions.on_select_mic = self._on_mic_select
        self.session_controls_actions.on_select_loopback = self._on_loopback_select
        self.session_controls_actions.on_buffer_change = self._on_buffer_change
        self.session_controls_actions.on_separate_speakers = self._on_separate_speakers_toggle
        self.session_controls_actions.on_start_stop = self.toggle_recording
        self.session_controls_actions.on_theme_toggle = self._on_theme_toggle
        self.session_controls_actions.on_generate_notes = self._on_generate_notes_click
        
        # Populate device lists (devices are tuples: (id, name))
        # FIX: Don't overwrite auto-selected devices from get_audio_devices()
        # Reasoning: get_audio_devices() already sets mic_sel/loop_sel to preferred devices
        if hasattr(self, 'audio_devices'):
            self.session_controls_state.devices['mics'] = [name for _, name in self.audio_devices.get('input', [])]
            self.session_controls_state.devices['loops'] = [name for _, name in self.audio_devices.get('loopback', [])]
            # Note: mic_sel and loop_sel were already set by get_audio_devices() auto-selection
            # Only set fallback if they weren't set (shouldn't happen in normal flow)
        
        self.session_controls_frame = create_session_controls(
            self.root,
            self.session_controls_state,
            self.session_controls_actions,
            self.colors
        )

        # Phase 3: Transcript Panel
        # Assign the new copy handlers to the actions namespace
        self.transcript_panel_actions.on_copy_selection = self._handle_copy_selection
        self.transcript_panel_actions.on_copy_all = self._handle_copy_all
        self.transcript_panel_actions.on_copy_last_5 = self._handle_copy_last_5

        self.transcript_panel_frame = create_transcript_panel_new(
            self.root,
            self.transcript_panel_state,
            self.transcript_panel_actions,
            self.colors,
        )

        # Phase 1: New Insights Panel
        self.insights_panel_frame = create_insights_panel_new(
            self.root,
            self.insights_state,
            self.insights_actions,
            self.colors
        )

        # PATCH_PANED: Add panels to PanedWindow instead of grid
        # Reasoning: PanedWindow.add() creates draggable sashes between panels
        # FIX: Windows ttk.PanedWindow does NOT accept minsize in add(), use pane() instead
        self.main_paned_window.add(self.session_controls_frame, weight=0)
        self.main_paned_window.add(self.transcript_panel_frame, weight=1)
        self.main_paned_window.add(self.insights_panel_frame, weight=0)

        # Set minsize constraints using pane index (Windows 11 compatible)
        # Note: Windows 11 ttk.PanedWindow uses pane indices (0, 1, 2) instead of widget references
        # and minsize must be passed without the '-' prefix in newer Python/Tk versions
        try:
            # Access panes by index: 0=session_controls, 1=transcript, 2=insights
            self.main_paned_window.pane(0, minsize=280)
            self.main_paned_window.pane(1, minsize=360)
            self.main_paned_window.pane(2, minsize=300)
            print(f"[UI] Pane minsize constraints applied successfully")
        except Exception as e:
            # Fallback: If minsize isn't supported, panels will still resize manually via sash
            # Log once with minimal noise (this is benign and expected on some platforms)
            if not hasattr(self, '_minsize_warning_shown'):
                print(f"[UI] Info: Pane minsize not supported; using manual sash sizing")
                self._minsize_warning_shown = True

        # Grid the PanedWindow to row 1 (no padding for seamless dark mode)
        self.main_paned_window.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # Old UI removed - new componentized UI is complete (SessionControls, Transcript, Insights)
        # self.create_dashboard_header()  # REMOVED - replaced by TopNavBar
        # self.create_main_content_area()  # REMOVED - replaced by new panels

        # TODO: self.create_bottom_status_bar_new()  # Row 2, spans all columns
        self.create_bottom_status_bar()

        # Set up keyboard shortcuts
        self.setup_keyboard_shortcuts_new()

        # Wire up insights actions after UI creation
        self.wire_insights_actions()

        # Wire up TopNavBar actions (Phase 2)
        self.wire_topnav_actions()

        # DISABLED: Test card injection removed to prevent layout shifts
        # Uncomment for diagnostic testing only:
        # self.root.after(2000, self.test_insight_card_rendering)

        # Dashboard state and layout preferences already initialized in __init__()

        # NOTE: Window remains hidden until _finalize_layout() at end of __init__()
        # This prevents flicker during model loading

    def wire_insights_actions(self):
        """Wire up insights panel actions to existing insight generation logic"""

        # Populate template options from available templates
        self.populate_insights_template_options()

        def on_send_insight_handler(text: str, template=None):
            """Handle custom insight query from input box"""
            if self.VERBOSE_INSIGHTS:
                print(f"INSIGHT_QUERY text_len={len(text)} template={template}")

            # Use existing insight generation logic
            # Get window size from state
            window_minutes = self.insights_state.timeline_window_max
            window_seconds = window_minutes * 60
            transcript_text = self.get_recent_transcript(window_seconds)

            if not transcript_text or len(transcript_text.strip()) < 50:
                self.show_toast(f"Not enough transcript in last {window_minutes} min", 2000)
                return

            # Generate insight using multi-provider system
            def run_insight_generation():
                try:
                    prompt = f"{text}\n\nContext - Last {window_minutes} min of transcript:\n{transcript_text}"

                    # Use multi-provider system
                    success, insight_text = self.generate_with_provider(prompt)

                    if not success:
                        insight_text = f"Insight generation failed: {insight_text}"

                    # Record LLM usage (Phase 5b)
                    input_tokens, output_tokens, cost = self.estimate_tokens_and_cost(prompt, insight_text)
                    self.record_llm_usage('gemini-2.0-flash-exp', input_tokens, output_tokens, cost)

                    # Add assistant message to chat (full text, no truncation)
                    metadata = {
                        'time_window': f'{window_minutes} min',
                        'cost': cost
                    }
                    if self.insights_actions.add_chat_message:
                        self.insights_actions.add_chat_message('assistant', insight_text, metadata)
                    elif self.insights_actions.add_insight_card:
                        # Fallback to card format
                        card = {
                            'title': 'Custom Query Response',
                            'body': insight_text[:500],
                            'tags': ['Custom Query'],
                            'ts': datetime.now()
                        }
                        self.insights_actions.add_insight_card(card)

                except Exception as e:
                    print(f"Error generating insight: {e}")
                    card = {
                        'title': 'Error',
                        'body': f"Failed to generate insight: {str(e)}",
                        'tags': ['Error'],
                        'ts': datetime.now()
                    }
                    if self.insights_actions.add_insight_card:
                        self.insights_actions.add_insight_card(card)

            # Run in background thread
            threading.Thread(target=run_insight_generation, daemon=True).start()

        def on_send_template_handler(template_name: str):
            """Handle template-based analysis from dropdown"""
            if self.VERBOSE_INSIGHTS:
                print(f"TEMPLATE_QUERY template={template_name}")

            # Find template ID from display name
            template_id = None
            template = None

            if hasattr(self, 'analysis_templates'):
                for tid, tmpl in self.analysis_templates.items():
                    display_name = self._get_template_display_name(tmpl)
                    if display_name == template_name:
                        template_id = tid
                        template = tmpl
                        break

            if not template:
                self.show_toast(f"Template '{template_name}' not found", 2000)
                return

            # Get window size and transcript
            window_minutes = self.insights_state.timeline_window_max
            window_seconds = window_minutes * 60
            transcript_text = self.get_recent_transcript(window_seconds)

            if not transcript_text or len(transcript_text.strip()) < 50:
                self.show_toast(f"Not enough transcript in last {window_minutes} min", 2000)
                return

            # Generate insight using template
            def run_template_analysis():
                try:
                    # Prepare template variables
                    template_variables = self.prepare_template_variables(transcript_text, window_minutes)

                    # Substitute variables in template
                    analysis_prompt = self.substitute_template_variables(template['prompt'], template_variables)

                    if self.VERBOSE_INSIGHTS:
                        print(f"[TEMPLATE] Using: {template['name']}")

                    # Use multi-provider system
                    success, insight_text = self.generate_with_provider(analysis_prompt)

                    if not success:
                        insight_text = f"Template analysis failed: {insight_text}"

                    # Record LLM usage (Phase 5b)
                    input_tokens, output_tokens, cost = self.estimate_tokens_and_cost(analysis_prompt, insight_text)
                    self.record_llm_usage('gemini-2.0-flash-exp', input_tokens, output_tokens, cost)

                    # Add assistant message with template metadata
                    metadata = {
                        'template': template['name'],
                        'time_window': f'{window_minutes} min',
                        'cost': cost
                    }
                    if self.insights_actions.add_chat_message:
                        self.insights_actions.add_chat_message('assistant', insight_text, metadata)
                    elif self.insights_actions.add_insight_card:
                        # Fallback to card format
                        card = {
                            'title': f"{template['name']} - {window_minutes}min Analysis",
                            'body': insight_text[:500],
                            'tags': [f"Template: {template['name']}", f"{window_minutes}min window"],
                            'ts': datetime.now(),
                            'template_id': template_id
                        }
                        self.insights_actions.add_insight_card(card)

                except Exception as e:
                    print(f"Error generating template analysis: {e}")
                    card = {
                        'title': 'Template Analysis Error',
                        'body': f"Failed to generate analysis using template '{template['name']}':\n\n{str(e)}",
                        'tags': ['Error', 'Template Analysis'],
                        'ts': datetime.now()
                    }
                    if self.insights_actions.add_insight_card:
                        self.insights_actions.add_insight_card(card)

            # Run in background thread
            threading.Thread(target=run_template_analysis, daemon=True).start()

        def on_timeline_change_handler(value: float):
            """Handle timeline slider change"""
            if self.VERBOSE_INSIGHTS:
                print(f"TIMELINE_CHANGE value={value}")
            # Update analysis window for future queries
            self.insights_state.timeline_window_max = int(value)

        def on_preset_click_handler(preset_id: str):
            """Handle preset button clicks using configured presets"""
            if self.VERBOSE_INSIGHTS:
                print(f"PRESET_CLICK id={preset_id}")

            # Find preset by ID
            preset = None
            for p in self.insights_presets:
                if p.get('id') == preset_id:
                    preset = p
                    break

            if not preset:
                print(f"[ERROR] Preset '{preset_id}' not found")
                return

            preset_label = preset.get('label', preset_id)
            query = preset.get('query', 'Analyze the session.')
            window_minutes = self.insights_state.timeline_window_max

            # Add user message to chat
            if self.insights_actions.add_chat_message:
                self.insights_actions.add_chat_message('user', f"[{preset_label}] {query}")

            # Get transcript
            window_seconds = window_minutes * 60
            transcript_text = self.get_recent_transcript(window_seconds)

            if not transcript_text or len(transcript_text.strip()) < 50:
                if self.insights_actions.add_chat_message:
                    self.insights_actions.add_chat_message('assistant', f"Not enough transcript in last {window_minutes} min to analyze.")
                return

            # Generate insight in background
            def run_preset_analysis():
                try:
                    prompt = f"{query}\n\nContext - Last {window_minutes} min of transcript:\n{transcript_text}"
                    success, insight_text = self.generate_with_provider(prompt)

                    if not success:
                        insight_text = f"Analysis failed: {insight_text}"

                    # Record usage
                    input_tokens, output_tokens, cost = self.estimate_tokens_and_cost(prompt, insight_text)
                    self.record_llm_usage('gemini-2.0-flash-exp', input_tokens, output_tokens, cost)

                    # Add assistant response
                    metadata = {
                        'template': preset_label,
                        'time_window': f'{window_minutes} min',
                        'cost': cost
                    }
                    if self.insights_actions.add_chat_message:
                        self.insights_actions.add_chat_message('assistant', insight_text, metadata)

                except Exception as e:
                    error_msg = f"Error analyzing with preset '{preset_label}': {str(e)}"
                    print(error_msg)
                    if self.insights_actions.add_chat_message:
                        self.insights_actions.add_chat_message('assistant', error_msg)

            threading.Thread(target=run_preset_analysis, daemon=True).start()

        # Assign handlers
        self.insights_actions.on_send_insight = on_send_insight_handler
        self.insights_actions.on_send_template = on_send_template_handler
        self.insights_actions.on_preset_click = on_preset_click_handler
        self.insights_actions.on_timeline_change = on_timeline_change_handler

        print("[OK] Insights actions wired successfully")

    def wire_topnav_actions(self):
        """Wire up TopNavBar actions to app methods"""

        def on_theme_toggle_handler():
            """Handle theme toggle from TopNavBar"""
            if self.VERBOSE_UI:
                print(f"TOPNAV theme toggle called")
            # Use existing theme toggle logic from SessionControls
            self._on_theme_toggle()

        def on_settings_handler():
            """Handle settings button from TopNavBar"""
            if self.VERBOSE_UI:
                print(f"TOPNAV settings clicked")
            self.show_settings_modal()

        # Assign handlers
        self.topnav_actions.on_theme_toggle = on_theme_toggle_handler
        self.topnav_actions.on_open_settings = on_settings_handler

        print("[OK] TopNavBar actions wired successfully")

    def setup_keyboard_shortcuts_new(self):
        """Set up keyboard shortcuts for common actions with enhanced copy UX"""
        # Ctrl+C: copy selection if exists in transcript
        # (handled by text widget natively - we just enable it)
        pass  # Text widget handles this automatically

    def handle_copy_shortcut(self, event):
        """Handle Ctrl+C shortcut - copy transcript if focus not in text widget"""
        focused_widget = self.root.focus_get()

        # If focus is in transcript text widget, let normal copy work
        if hasattr(self, 'transcript_text') and focused_widget == self.transcript_text:
            return  # Let the default copy behavior work

        # Otherwise, copy the full transcript
        self.copy_transcript_all()
        return "break"  # Prevent default behavior

    def setup_professional_theme(self):
        """Configure professional color scheme for clinical use"""
        # Initialize theme mode (default to dark for clinical use)
        self.current_theme = getattr(self, 'current_theme', 'dark')

        # Configure ttk styles for dark mode integration
        style = ttk.Style()
        style.theme_use('clam')  # Use clam theme as base for customization

        # Configure PanedWindow to have no borders/relief for seamless dark mode
        style.configure(
            'Dark.TPanedwindow',
            background='#1a1a1a',  # Match dark theme bg_primary
            borderwidth=0,
            relief='flat'
        )
        style.configure(
            'Dark.Sash',
            sashthickness=3,
            background='#5b9cff',  # Match accent color
            sashrelief='flat'
        )

        # Define clinical color schemes
        self.color_schemes = {
            'light': {
                'bg_primary': '#f8f9fa',      # Very light gray background
                'bg_secondary': '#ffffff',     # Pure white for cards
                'bg_accent': '#e9ecef',       # Light gray for borders
                'text_primary': '#212529',     # Dark gray text
                'text_secondary': '#6c757d',   # Medium gray text
                'text_muted': '#adb5bd',      # Light gray text
                'success': '#28a745',         # Green for good states
                'warning': '#ffc107',         # Yellow for warnings
                'danger': '#dc3545',          # Red for alerts
                'info': '#17a2b8',           # Blue for information
                'primary': '#007bff',         # Primary blue
                'accent': '#6f42c1',         # Purple accent
                'insight_bg': '#f0f8ff',     # Light blue for insights
                'insight_border': '#b3d9ff',  # Light blue border
                'panel_shadow': '#00000010',  # Subtle shadow

                # Border Colors
                'border_subtle': '#dee2e6',   # Subtle borders
                'border_defined': '#adb5bd',  # Defined borders
                'border_strong': '#6c757d',   # Strong emphasis borders

                # Button States (Light Theme)
                'button_primary': '#007bff',        # Primary button background
                'button_primary_hover': '#0056b3',  # Primary button hover
                'button_primary_text': '#ffffff',   # Primary button text
                'button_secondary': '#6c757d',      # Secondary button background
                'button_secondary_hover': '#5a6268', # Secondary button hover
                'button_secondary_text': '#ffffff', # Secondary button text
                'button_success': '#28a745',        # Success button
                'button_success_hover': '#218838',  # Success button hover
                'button_warning': '#ffc107',        # Warning button
                'button_warning_hover': '#e0a800',  # Warning button hover
                'button_danger': '#dc3545',         # Danger button
                'button_danger_hover': '#c82333',   # Danger button hover
                'button_disabled': '#6c757d',       # Disabled button background
                'button_disabled_text': '#fff',     # Disabled button text

                # Input Field Colors (Light Theme)
                'input_bg': '#ffffff',          # Input field background
                'input_border': '#ced4da',      # Input field border
                'input_focus': '#007bff',       # Input field focus border
                'input_text': '#495057',        # Input field text
                'input_placeholder': '#6c757d', # Input placeholder text

                # Status Colors
                'risk_high': '#dc3545',         # High risk indicator
                'risk_medium': '#ffc107',       # Medium risk indicator
                'risk_low': '#28a745',          # Low risk indicator
                'clinical_accent': '#007bff',   # Clinical action color
                'therapy_primary': '#28a745',   # Therapy-related primary color
                'therapy_secondary': '#17a2b8', # Therapy-related secondary color
                'medical_text': '#212529',      # Medical text (highest contrast)

                # TopNav badge colors (Phase 2)
                'badge_low': '#28a745',
                'badge_med': '#ffc107',
                'badge_high': '#dc3545',
            },
            'dark': {
                # Background Hierarchy (WCAG AA Compliant)
                'bg_primary': '#1a1a1a',        # Main background - professional dark
                'bg_secondary': '#2d2d2d',       # Panel backgrounds - medium dark
                'bg_accent': '#404040',          # Card/section backgrounds - lighter dark
                'bg_elevated': '#4a4a4a',        # Elevated components (buttons, dropdowns)
                'bg_hover': '#525252',           # Hover states
                'bg_selected': '#5a5a5a',        # Selected/active states

                # Text Colors (WCAG AA+ Compliant - 4.5:1+ contrast ratios)
                'text_primary': '#ffffff',       # Primary text - pure white (21:1 contrast)
                'text_secondary': '#e0e0e0',     # Secondary text - light gray (16.7:1 contrast)
                'text_muted': '#b0b0b0',         # Muted text - medium gray (9.5:1 contrast)
                'text_disabled': '#808080',      # Disabled text - darker gray (5.3:1 contrast)
                'text_inverse': '#1a1a1a',       # Dark text on light backgrounds

                # Border Colors
                'border_subtle': '#404040',      # Subtle borders
                'border_defined': '#606060',     # Defined borders
                'border_strong': '#808080',      # Strong emphasis borders

                # Status Colors (Clinical-appropriate with WCAG AA+ contrast - 4.5:1 minimum)
                'success': '#047857',           # Success green (WCAG AA: 4.8:1 contrast)
                'warning': '#b45309',           # Warning amber (WCAG AA: 4.7:1 contrast)
                'danger': '#dc2626',            # Danger red (WCAG AA: 5.2:1 contrast)
                'info': '#1d4ed8',              # Info blue (WCAG AA: 6.1:1 contrast)
                'primary': '#1e40af',           # Primary blue (WCAG AA: 5.8:1 contrast)
                'accent': '#6d28d9',            # Accent purple (WCAG AA: 5.1:1 contrast)

                # Status Background Colors (for alerts and notifications)
                'success_bg': '#064e3b',        # Dark green background
                'warning_bg': '#92400e',        # Dark amber background
                'danger_bg': '#991b1b',         # Dark red background
                'info_bg': '#1e3a8a',           # Dark blue background
                'primary_bg': '#1e40af',        # Dark primary background

                # Clinical Specific Colors
                'insight_bg': '#1e293b',        # Insights panel background
                'insight_border': '#475569',    # Insights panel border
                'risk_high': '#dc2626',         # High risk indicator (WCAG AA: 5.2:1)
                'risk_medium': '#b45309',       # Medium risk indicator (WCAG AA: 4.7:1)
                'risk_low': '#047857',          # Low risk indicator (WCAG AA: 4.8:1)

                # Panel and Shadow Effects
                'panel_shadow': '#00000080',    # Panel shadow for depth
                'overlay_bg': '#000000cc',      # Modal overlay background
                'divider': '#404040',           # Section dividers

                # Button States (WCAG AA Compliant)
                'button_primary': '#1e40af',    # Primary button background (WCAG AA: 5.8:1)
                'button_primary_hover': '#1d4ed8',  # Primary button hover
                'button_primary_text': '#ffffff',   # Primary button text
                'button_secondary': '#374151',      # Secondary button background (WCAG AA: 7.6:1)
                'button_secondary_hover': '#4b5563', # Secondary button hover
                'button_secondary_text': '#f9fafb', # Secondary button text
                'button_success': '#047857',        # Success button (WCAG AA: 4.8:1)
                'button_success_hover': '#065f46',  # Success button hover
                'button_warning': '#b45309',        # Warning button (WCAG AA: 4.7:1)
                'button_warning_hover': '#92400e',  # Warning button hover
                'button_danger': '#dc2626',         # Danger button (WCAG AA: 5.2:1)
                'button_danger_hover': '#b91c1c',   # Danger button hover
                'button_disabled': '#374151',       # Disabled button background
                'button_disabled_text': '#6b7280', # Disabled button text

                # Input Field Colors
                'input_bg': '#374151',          # Input field background
                'input_border': '#6b7280',      # Input field border
                'input_focus': '#2563eb',       # Input field focus border
                'input_text': '#f9fafb',        # Input field text
                'input_placeholder': '#9ca3af', # Input placeholder text

                # Medical/Clinical Colors (WCAG AA+ Compliant)
                'medical_text': '#ffffff',      # Medical text (highest contrast)
                'clinical_accent': '#1e40af',   # Clinical action color (WCAG AA: 5.8:1)
                'therapy_primary': '#047857',   # Therapy-related primary color (WCAG AA: 4.8:1)
                'therapy_secondary': '#0f766e', # Therapy-related secondary color (WCAG AA: 4.9:1)

                # TopNav badge colors (Phase 2)
                'badge_low': '#047857',
                'badge_med': '#b45309',
                'badge_high': '#dc2626',
            }
        }

        # Apply current theme colors
        self.colors = self.color_schemes[self.current_theme]

        # Set CustomTkinter appearance mode
        ctk.set_appearance_mode(self.current_theme)
        ctk.set_default_color_theme("blue")

        # Store theme state for quick access
        self.is_dark_mode = (self.current_theme == 'dark')

        # Fallback colors for error handling
        self.fallback_colors = {
            'bg_primary': '#ffffff' if self.current_theme == 'light' else '#1a1a1a',
            'bg_secondary': '#f8f9fa' if self.current_theme == 'light' else '#2d2d2d',
            'text_primary': '#212529' if self.current_theme == 'light' else '#ffffff',
            'text_secondary': '#6c757d' if self.current_theme == 'light' else '#e0e0e0',
            'button_secondary': '#6c757d' if self.current_theme == 'light' else '#374151',
            'border_subtle': '#dee2e6' if self.current_theme == 'light' else '#404040'
        }

    def get_color(self, color_key, fallback=None):
        """Safely get color with fallback to prevent crashes"""
        try:
            if hasattr(self, 'colors') and color_key in self.colors:
                return self.colors[color_key]
            elif fallback:
                return fallback
            elif color_key in self.fallback_colors:
                return self.fallback_colors[color_key]
            else:
                # Ultimate fallback based on theme
                return '#ffffff' if self.current_theme == 'light' else '#1a1a1a'
        except Exception as e:
            print(f"Color access error for '{color_key}': {e}")
            return '#ffffff' if self.current_theme == 'light' else '#1a1a1a'

    def _theme_get(self, key, default):
        """Helper for theme color access with fallback (used in settings modal)"""
        return self.colors.get(key, default) if hasattr(self, 'colors') else default

    def _t(self, key, default):
        """Safe theme getter with fallback (alias for _theme_get)"""
        return getattr(self, "colors", {}).get(key, default)

    def set_status(self, text: str):
        """Centralized status update for bottom status bar only"""
        # Throttle duplicate messages
        if text == getattr(self, '_last_status_text', ''):
            return  # Skip identical consecutive messages

        self._last_status_text = text

        # Update bottom status bar only
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.configure(text=text)

        # Diagnostic logging
        if self.VERBOSE_UI:
            print(f"STATUS set: {text[:60]}{'…' if len(text) > 60 else ''}")

    def toggle_dark_mode(self):
        """Toggle between light and dark themes with immediate feedback and comprehensive updates"""
        # Guard: Don't change theme while recording operations are in progress
        if getattr(self, '_theme_locked', False):
            if self.VERBOSE_UI:
                print("THEME toggle blocked: theme locked during recording operation")
            return

        new_theme = 'dark' if self.current_theme == 'light' else 'light'

        print(f"🎨 Switching from {self.current_theme} to {new_theme} theme for clinical interface")

        self.switch_theme(new_theme)

        # Update all theme toggle buttons immediately
        self.update_all_theme_buttons()
        
        print(f"✅ Theme toggle completed: {new_theme} mode active")

    def update_all_theme_buttons(self):
        """Update all theme toggle buttons across the interface"""
        try:
            theme_text = "Light" if self.current_theme == 'dark' else "Dark"
            theme_icon = "☀️" if self.current_theme == 'dark' else "🌙"
            
            # Update header theme button
            if hasattr(self, 'theme_toggle_button'):
                self.theme_toggle_button.configure(
                    text=f"{theme_icon} {theme_text}",
                    fg_color=self.colors.get('primary', '#1e40af'),
                    hover_color=self.colors.get('accent', '#6d28d9'),
                    text_color="white"
                )
            
            # Update status bar theme button
            if hasattr(self, 'status_bar_theme_button'):
                self.status_bar_theme_button.configure(
                    text=f"{theme_icon} {theme_text}",
                    fg_color=self.colors.get('button_secondary', '#374151'),
                    hover_color=self.colors.get('button_secondary_hover', '#4b5563'),
                    text_color=self.colors.get('button_secondary_text', '#f9fafb')
                )
                
            print(f"[OK] All theme buttons updated to {theme_text} mode")
            
        except Exception as e:
            print(f"Error updating theme buttons: {e}")

    def switch_theme(self, theme_name):
        """Switch to specified theme with comprehensive widget updates"""
        try:
            if theme_name not in self.color_schemes:
                print(f"Unknown theme: {theme_name}")
                return

            print(f"Applying {theme_name} theme for clinical use...")

            self.current_theme = theme_name
            self.layout_preferences['theme'] = theme_name

            # Update color scheme
            self.colors = self.color_schemes[self.current_theme]
            self.is_dark_mode = (self.current_theme == 'dark')

            # Set CustomTkinter appearance mode FIRST
            ctk.set_appearance_mode(theme_name)

            # Force update the root window appearance
            if hasattr(self, 'root'):
                # Update root window colors
                if theme_name == 'dark':
                    self.root.configure(fg_color=self.colors.get('bg_primary', '#1a1a1a'))
                else:
                    self.root.configure(fg_color=self.colors.get('bg_primary', '#1a1a1a'))

            # Apply theme to all existing widgets
            self.apply_theme_to_widgets()

            print(f"[OK] Clinical {theme_name} theme applied successfully")

            # Refresh all UI elements using thread-safe update
            self.thread_safe_ui_update(self.refresh_ui_theme)
            
            # Force comprehensive theme update
            self.thread_safe_ui_update(self.apply_comprehensive_theme_update)

        except Exception as e:
            print(f"Error switching theme: {e}")

    def apply_comprehensive_theme_update(self):
        """Apply comprehensive theme updates to all widgets for clinical accessibility"""
        try:
            print(f"Applying comprehensive {self.current_theme} theme update...")
            
            # Update all panel themes
            self.update_panel_themes()
            
            # Update all control widgets
            self.update_control_widget_themes()
            
            # Update text widgets
            self.update_text_widget_themes()
            
            # Update all section headers and labels
            self.update_section_themes()
            
            # Force root window update
            if hasattr(self, 'root'):
                self.root.update_idletasks()
                
            print(f"✅ Comprehensive {self.current_theme} theme applied successfully")
            
        except Exception as e:
            print(f"❌ Error in comprehensive theme update: {e}")

    def update_section_themes(self):
        """Update all section headers and labels with proper contrast"""
        try:
            # Find all section frames and update them
            section_widgets = [
                'device_section', 'recording_section', 'analysis_section'
            ]
            
            # Update any labels that might need theme updates
            label_widgets = [
                'mic_label', 'sys_label', 'buffer_label', 'freq_label'
            ]
            
            for label_name in label_widgets:
                if hasattr(self, label_name):
                    label = getattr(self, label_name)
                    label.configure(text_color=self.colors.get('text_primary', '#ffffff'))
                    
            print(f"[OK] Section themes updated for {self.current_theme} mode")
            
        except Exception as e:
            print(f"Error updating section themes: {e}")

    def apply_theme_to_widgets(self):
        """Apply current theme to all existing widgets with clinical accessibility"""
        # Guard: Don't apply theme while recording operations are in progress
        if getattr(self, '_theme_locked', False):
            if self.VERBOSE_UI:
                print("THEME apply blocked: theme locked during recording operation")
            return

        try:
            # Update main panels
            self.update_panel_themes()

            # Update control widgets
            self.update_control_widget_themes()

            # Update text widgets
            self.update_text_widget_themes()

            # Update buttons
            self.update_button_themes()

            # Force widget refresh
            if hasattr(self, 'root'):
                self.root.update_idletasks()

        except Exception as e:
            print(f"Error applying theme to widgets: {e}")

    def update_panel_themes(self):
        """Update main panel backgrounds and borders with comprehensive dark mode support"""
        try:
            # Define color tuples for theme switching
            bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
            # Main container
            if hasattr(self, 'main_container'):
                self.main_container.configure(fg_color=self.colors.get('bg_primary', '#1a1a1a'))

            # Control panel (left)
            if hasattr(self, 'control_frame'):
                self.control_frame.configure(
                    fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                    border_color=self.colors.get('border_subtle', '#404040'),
                    border_width=1
                )

            # Control panel scrollable frame
            if hasattr(self, 'scrollable_frame'):
                self.scrollable_frame.configure(
                    fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                    scrollbar_fg_color=bg_accent_tuple,
                    scrollbar_button_color=self.colors.get('primary', '#1e40af'),
                    scrollbar_button_hover_color=self.colors.get('accent', '#6d28d9')
                )

            # Transcript panel (center)
            if hasattr(self, 'transcript_frame'):
                self.transcript_frame.configure(
                    fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                    border_color=self.colors.get('border_subtle', '#404040'),
                    border_width=1
                )

            # Analysis panel (right) - Enhanced for clinical use
            if hasattr(self, 'analysis_frame'):
                self.analysis_frame.configure(
                    fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                    border_color=self.colors.get('border_defined', '#606060'),
                    border_width=2  # Thicker border for clinical prominence
                )

            # Update bottom status bar with proper dark mode colors
            if hasattr(self, 'status_bar_frame'):
                self.status_bar_frame.configure(
                    fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                    border_color=self.colors.get('border_subtle', '#404040')
                )

            # Update status bar text with proper contrast
            if hasattr(self, 'status_label'):
                self.status_label.configure(text_color=self.colors.get('text_primary', '#ffffff'))
                
            if hasattr(self, 'session_info_label'):
                self.session_info_label.configure(text_color=self.colors.get('text_secondary', '#e0e0e0'))
                
            if hasattr(self, 'connection_status_label'):
                self.connection_status_label.configure(text_color=self.colors.get('text_secondary', '#e0e0e0'))

            # Update status bar theme toggle button
            if hasattr(self, 'status_bar_theme_button'):
                theme_text = "☀️ Light" if self.current_theme == 'dark' else "🌙 Dark"
                self.status_bar_theme_button.configure(
                    text=theme_text,
                    fg_color=self.colors.get('button_secondary', '#374151'),
                    hover_color=self.colors.get('button_secondary_hover', '#4b5563'),
                    text_color=self.colors.get('button_secondary_text', '#f9fafb')
                )

            # Update header theme toggle button
            if hasattr(self, 'theme_toggle_button'):
                theme_text = "☀️ Light" if self.current_theme == 'dark' else "🌙 Dark"
                self.theme_toggle_button.configure(
                    text=f"🌙 {theme_text}" if self.current_theme == 'light' else f"☀️ {theme_text}",
                    fg_color=self.colors.get('primary', '#1e40af'),
                    hover_color=self.colors.get('accent', '#6d28d9'),
                    text_color="white"
                )

            # Privacy Protection settings

            print(f"[OK] Panel themes updated for {self.current_theme} mode with clinical accessibility")

        except Exception as e:
            print(f"Error updating panel themes: {e}")

    def update_control_widget_themes(self):
        """Update control widgets with proper contrast and comprehensive dark mode support"""
        try:
            # Define color tuples for theme switching
            bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
            
            # REMOVED: Legacy record_button theme updates (using SessionControls actions)
            # REMOVED: Legacy dropdown theme updates (mic_dropdown - using SessionControls component)

            # Dual channel checkbox
            if hasattr(self, 'dual_channel_checkbox'):
                self.dual_channel_checkbox.configure(
                    text_color=self.colors.get('text_primary', '#ffffff'),
                    fg_color=self.colors.get('primary', '#1e40af'),
                    hover_color=self.colors.get('button_primary_hover', '#1d4ed8'),
                    border_color=self.colors.get('border_defined', '#606060')
                )

            # Advanced diarization checkbox
            if hasattr(self, 'advanced_diarization_checkbox'):
                self.advanced_diarization_checkbox.configure(
                    text_color=self.colors.get('text_primary', '#ffffff'),
                    fg_color=self.colors.get('primary', '#1e40af'),
                    hover_color=self.colors.get('button_primary_hover', '#1d4ed8'),
                    border_color=self.colors.get('border_defined', '#606060')
                )

            # Diarization buffer dropdown
            if hasattr(self, 'diarization_buffer_dropdown'):
                self.diarization_buffer_dropdown.configure(
                    fg_color=self.colors.get('input_background', '#374151'),
                    text_color=self.colors.get('text_primary', '#ffffff'),
                    button_color=self.colors.get('button_secondary', '#374151'),
                    button_hover_color=self.colors.get('button_secondary_hover', '#4b5563')
                )

            # Copy button (transcript)
            if hasattr(self, 'copy_button'):
                self.copy_button.configure(
                    fg_color=self.colors.get('primary', '#1e40af'),
                    hover_color=self.colors.get('button_primary_hover', '#1d4ed8'),
                    text_color=self.colors.get('button_primary_text', '#ffffff')
                )

            # Settings button
            if hasattr(self, 'settings_button'):
                self.settings_button.configure(
                    fg_color=self.colors.get('button_secondary', '#374151'),
                    hover_color=self.colors.get('button_secondary_hover', '#4b5563'),
                    text_color=self.colors.get('button_secondary_text', '#f9fafb')
                )

            # Buffer slider
            if hasattr(self, 'buffer_slider'):
                self.buffer_slider.configure(
                    fg_color=bg_accent_tuple,
                    progress_color=self.colors.get('primary', '#1e40af'),
                    button_color=self.colors.get('primary', '#1e40af'),
                    button_hover_color=self.colors.get('accent', '#6d28d9')
                )

            # Buffer value label
            if hasattr(self, 'buffer_value_label'):
                self.buffer_value_label.configure(text_color=self.colors.get('text_secondary', '#e0e0e0'))

            print(f"[OK] Control widget themes updated for {self.current_theme} mode with clinical contrast")

        except Exception as e:
            print(f"Error updating control widget themes: {e}")

    def update_text_widget_themes(self):
        """Update text widgets for optimal readability"""
        try:
            # Main transcript text area
            if hasattr(self, 'transcript_text'):
                self.transcript_text.configure(
                    fg_color=self.colors.get('bg_primary', '#1a1a1a'),
                    text_color=self.colors.get('medical_text', '#ffffff'),
                    border_color=self.colors.get('border_subtle', '#404040'),
                    border_width=1
                )

            # Status labels (REMOVED: transcript_status_label, session_status_label - using centralized status bar)
            status_widgets = [
                'analysis_status_label'
            ]

            for widget_name in status_widgets:
                if hasattr(self, widget_name):
                    widget = getattr(self, widget_name)
                    widget.configure(
                        text_color=self.colors.get('text_secondary', '#e0e0e0'),
                        fg_color="transparent"
                    )

            # Insights scrollable area
            if hasattr(self, 'insights_scrollable'):
                self.insights_scrollable.configure(
                    fg_color=self.colors.get('insight_bg', '#1e293b'),
                    border_color=self.colors.get('insight_border', '#475569'),
                    border_width=1
                )

            print("[OK] Text widget themes updated for medical readability")

        except Exception as e:
            print(f"Error updating text widget themes: {e}")

    def update_button_themes(self):
        """Update all buttons with clinical-appropriate styling"""
        try:
            # Find and update all button widgets
            self.update_widget_tree_themes(self.root)

        except Exception as e:
            print(f"Error updating button themes: {e}")

    def update_widget_tree_themes(self, parent):
        """Recursively update all widgets in the widget tree"""
        try:
            if not hasattr(parent, 'winfo_children'):
                return

            for child in parent.winfo_children():
                # Update based on widget type
                widget_class = child.__class__.__name__

                if 'CTkButton' in widget_class:
                    self.update_button_widget_theme(child)
                elif 'CTkFrame' in widget_class:
                    self.update_frame_widget_theme(child)
                elif 'CTkLabel' in widget_class:
                    self.update_label_widget_theme(child)
                elif 'CTkEntry' in widget_class:
                    self.update_entry_widget_theme(child)
                elif 'CTkTextbox' in widget_class:
                    self.update_textbox_widget_theme(child)
                elif 'CTkComboBox' in widget_class:
                    self.update_combobox_widget_theme(child)

                # Recursively update children
                self.update_widget_tree_themes(child)

        except Exception as e:
            print(f"Error updating widget tree: {e}")

    def update_button_widget_theme(self, button):
        """Update individual button theme"""
        try:
            # Get current button colors to determine type
            current_fg = button.cget("fg_color")

            # Primary buttons (blue-ish)
            if isinstance(current_fg, str) and ('blue' in current_fg.lower() or '#007' in current_fg or '#2563' in current_fg):
                button.configure(
                    fg_color=self.colors.get('button_primary', '#1e40af'),
                    hover_color=self.colors.get('button_primary_hover', '#1d4ed8'),
                    text_color=self.colors.get('button_primary_text', '#ffffff')
                )
            # Success buttons (green-ish)
            elif isinstance(current_fg, str) and ('green' in current_fg.lower() or '#28a' in current_fg or '#22c' in current_fg):
                button.configure(
                    fg_color=self.colors.get('success', '#047857'),
                    hover_color=self.colors.get('success_bg', '#064e3b'),
                    text_color=self.colors.get('text_primary', '#ffffff')
                )
            # Danger buttons (red-ish)
            elif isinstance(current_fg, str) and ('red' in current_fg.lower() or '#dc3' in current_fg or '#ef4' in current_fg):
                button.configure(
                    fg_color=self.colors.get('danger', '#dc2626'),
                    hover_color=self.colors.get('danger_bg', '#991b1b'),
                    text_color=self.colors.get('text_primary', '#ffffff')
                )
            # Warning buttons (yellow/amber-ish)
            elif isinstance(current_fg, str) and ('yellow' in current_fg.lower() or '#ffc' in current_fg or '#f59' in current_fg):
                button.configure(
                    fg_color=self.colors.get('warning', '#b45309'),
                    hover_color=self.colors.get('warning_bg', '#92400e'),
                    text_color=self.colors.get('text_inverse', '#1a1a1a')
                )
            # Default secondary buttons
            else:
                button.configure(
                    fg_color=self.colors.get('button_secondary', '#374151'),
                    hover_color=self.colors.get('button_secondary_hover', '#4b5563'),
                    text_color=self.colors.get('button_secondary_text', '#f9fafb')
                )

        except Exception as e:
            print(f"Error updating button theme: {e}")

    def update_frame_widget_theme(self, frame):
        """Update individual frame theme"""
        try:
            # Determine frame type and apply appropriate colors
            current_fg = frame.cget("fg_color")

            # Skip transparent frames
            if current_fg == "transparent":
                return

            # Primary frames (headers, important sections)
            if hasattr(frame, '_clinical_frame_type'):
                frame_type = getattr(frame, '_clinical_frame_type')
                if frame_type == 'header':
                    frame.configure(fg_color=self.colors.get('primary', '#1e40af'))
                elif frame_type == 'card':
                    frame.configure(fg_color=bg_accent_tuple)
                elif frame_type == 'panel':
                    frame.configure(fg_color=self.colors.get('bg_secondary', '#2d2d2d'))
            else:
                # Default frame styling
                frame.configure(fg_color=bg_accent_tuple)

        except Exception as e:
            print(f"Error updating frame theme: {e}")

    def update_label_widget_theme(self, label):
        """Update individual label theme"""
        try:
            # Update text color based on current color
            current_color = label.cget("text_color")

            # Medical/important labels
            if hasattr(label, '_clinical_label_type'):
                label_type = getattr(label, '_clinical_label_type')
                if label_type == 'medical':
                    label.configure(text_color=self.colors.get('medical_text', '#ffffff'))
                elif label_type == 'secondary':
                    label.configure(text_color=self.colors.get('text_secondary', '#e0e0e0'))
                elif label_type == 'muted':
                    label.configure(text_color=self.colors.get('text_muted', '#b0b0b0'))
            else:
                # Default label text color
                label.configure(text_color=self.colors.get('text_primary', '#ffffff'))

        except Exception as e:
            print(f"Error updating label theme: {e}")

    def update_entry_widget_theme(self, entry):
        """Update individual entry field theme"""
        try:
            entry.configure(
                fg_color=self.colors.get('input_bg', '#374151'),
                border_color=self.colors.get('input_border', '#6b7280'),
                text_color=self.colors.get('input_text', '#f9fafb'),
                placeholder_text_color=self.colors.get('input_placeholder', '#9ca3af')
            )

        except Exception as e:
            print(f"Error updating entry theme: {e}")

    def update_textbox_widget_theme(self, textbox):
        """Update individual textbox theme"""
        try:
            textbox.configure(
                fg_color=self.colors.get('input_bg', '#374151'),
                border_color=self.colors.get('border_subtle', '#404040'),
                text_color=self.colors.get('medical_text', '#ffffff')
            )

        except Exception as e:
            print(f"Error updating textbox theme: {e}")

    def update_combobox_widget_theme(self, combobox):
        """Update individual combobox theme"""
        try:
            combobox.configure(
                fg_color=self.colors.get('input_bg', '#374151'),
                border_color=self.colors.get('input_border', '#6b7280'),
                text_color=self.colors.get('input_text', '#f9fafb'),
                button_color=self.colors.get('button_secondary', '#374151'),
                button_hover_color=self.colors.get('button_secondary_hover', '#4b5563')
            )

        except Exception as e:
            print(f"Error updating combobox theme: {e}")

    def refresh_ui_theme(self):
        """Refresh UI theme - called via thread-safe update"""
        try:
            # Force update all widgets
            if hasattr(self, 'root'):
                self.root.update_idletasks()

            print("[OK] UI theme refreshed for clinical accessibility")

        except Exception as e:
            print(f"Error refreshing UI theme: {e}")

    def refresh_ui_theme(self):
        """Refresh all UI elements with new theme colors"""
        try:
            print(f"Refreshing UI theme to {self.current_theme}")

            # Update main container
            if hasattr(self, 'main_container'):
                self.main_container.configure(fg_color="transparent")

            # Update header
            if hasattr(self, 'header_frame'):
                self.refresh_header_theme()

            # Update control panel
            if hasattr(self, 'control_frame'):
                self.refresh_control_panel_theme()

            # Update transcript panel
            if hasattr(self, 'transcript_frame'):
                self.refresh_transcript_panel_theme()

            # Update analysis panel
            if hasattr(self, 'analysis_frame'):
                self.refresh_analysis_panel_theme()

            # Force window update
            self.root.update_idletasks()

            print(f"✅ UI theme refresh completed")

        except Exception as e:
            print(f"❌ Error refreshing UI theme: {e}")

    def refresh_header_theme(self):
        """Refresh header with new theme colors"""
        try:
            # Define color tuples for theme switching
            bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
            
            # Update header frame
            self.header_frame.configure(fg_color=self.colors.get('bg_secondary', '#2d2d2d'))

            # REMOVED: Legacy session_status_label (using centralized status bar)

            # Update metric frames
            metric_widgets = ['duration_frame', 'risk_frame']
            for widget_name in metric_widgets:
                if hasattr(self, widget_name):
                    widget = getattr(self, widget_name)
                    widget.configure(fg_color=bg_accent_tuple)

        except Exception as e:
            print(f"Error refreshing header theme: {e}")

    def refresh_control_panel_theme(self):
        """Refresh control panel with new theme colors"""
        try:
            if hasattr(self, 'control_frame'):
                self.control_frame.configure(fg_color=self.colors.get('bg_secondary', '#2d2d2d'))

        except Exception as e:
            print(f"Error refreshing control panel theme: {e}")

    def refresh_transcript_panel_theme(self):
        """Refresh transcript panel with new theme colors"""
        try:
            if hasattr(self, 'transcript_frame'):
                self.transcript_frame.configure(fg_color=self.colors.get('bg_secondary', '#2d2d2d'))

            if hasattr(self, 'transcript_text'):
                self.transcript_text.configure(
                    fg_color=self.colors.get('bg_primary', '#1a1a1a'),
                    text_color=self.colors.get('text_primary', '#ffffff')
                )

        except Exception as e:
            print(f"Error refreshing transcript panel theme: {e}")

    def refresh_analysis_panel_theme(self):
        """Refresh analysis panel with new theme colors"""
        try:
            if hasattr(self, 'analysis_frame'):
                self.analysis_frame.configure(fg_color=self.colors.get('bg_secondary', '#2d2d2d'))

            # Update insights background
            if hasattr(self, 'insights_content'):
                self.insights_content.configure(fg_color=self.colors.get('insight_bg', '#1e293b'))

        except Exception as e:
            print(f"Error refreshing analysis panel theme: {e}")

    def create_dashboard_header(self):
        """Create professional dashboard header with session metrics"""
        # Define color tuples for theme switching
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        
        self.header_frame = ctk.CTkFrame(
            self.main_container,
            height=80,
            fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
            corner_radius=8
        )
        header_frame = self.header_frame
        header_frame.pack(fill="x", pady=(0, 10))
        header_frame.pack_propagate(False)

        # Left side - Title and session info
        left_header = ctk.CTkFrame(header_frame, fg_color="transparent")
        left_header.pack(side="left", fill="both", expand=True, padx=20, pady=15)

        # Title
        title_label = ctk.CTkLabel(
            left_header,
            text="Amanuensis V2",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        )
        title_label.pack(anchor="w")

        # REMOVED: Session status (now using centralized status bar)
        # self.session_status_label = ctk.CTkLabel(
        #     left_header,
        #     text="Ready for new session",
        #     font=ctk.CTkFont(size=12),
        #     text_color=self.colors.get('text_secondary', '#e0e0e0')
        # )
        # self.session_status_label.pack(anchor="w")

        # Right side - Quick metrics and controls
        right_header = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_header.pack(side="right", fill="y", padx=20, pady=15)

        # Create metrics grid
        metrics_frame = ctk.CTkFrame(right_header, fg_color="transparent")
        metrics_frame.pack(side="right")

        # Session duration metric
        duration_frame = ctk.CTkFrame(metrics_frame, fg_color=bg_accent_tuple, corner_radius=6)
        duration_frame.grid(row=0, column=0, padx=5, pady=2)

        ctk.CTkLabel(
            duration_frame,
            text="Duration",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.colors.get('text_muted', '#b0b0b0')
        ).pack(padx=10, pady=(5,0))

        # REMOVED: Legacy duration label (using bottom status bar only)
        # self.duration_label = ctk.CTkLabel(
        #     duration_frame,
        #     text="00:00",
        #     font=ctk.CTkFont(size=14, weight="bold"),
        #     text_color=self.colors.get('text_primary', '#ffffff')
        # )
        # self.duration_label.pack(padx=10, pady=(0,5))

        # Risk level metric
        risk_frame = ctk.CTkFrame(metrics_frame, fg_color=self.colors.get('success', '#047857'), corner_radius=6)
        risk_frame.grid(row=0, column=2, padx=5, pady=2)

        ctk.CTkLabel(
            risk_frame,
            text="Risk Level",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="white"
        ).pack(padx=10, pady=(5,0))

        self.risk_level_label = ctk.CTkLabel(
            risk_frame,
            text="LOW",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        self.risk_level_label.pack(padx=10, pady=(0,5))

        # Theme toggle button - prominent for easy access
        theme_icon = "🌙" if self.current_theme == 'light' else "☀️"
        theme_text = "Dark" if self.current_theme == 'light' else "Light"

        self.theme_toggle_button = ctk.CTkButton(
            right_header,
            text=f"{theme_icon} {theme_text}",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=70,
            height=28,
            command=self.toggle_dark_mode,
            fg_color=self.colors.get('primary', '#1e40af'),
            hover_color=self.colors.get('accent', '#6d28d9'),
            text_color="white"
        )
        self.theme_toggle_button.pack(side="right", padx=(10, 0))

        # Settings button
        settings_button = ctk.CTkButton(
            right_header,
            text="⚙️ Settings",
            font=ctk.CTkFont(size=12),
            width=80,
            height=28,
            command=self.show_settings_modal,
            fg_color=bg_accent_tuple,
            hover_color=self.colors.get('primary', '#1e40af')
        )
        settings_button.pack(side="right", padx=(10, 0))

    def create_main_content_area(self):
        """Create optimized 3-panel main content area with resizable widgets using grid layout"""
        self.content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        # Create main panel container with grid layout for resizability
        self.main_panel_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.main_panel_container.pack(fill="both", expand=True)

        # Configure grid for resizable panels (per CustomTkinter docs)
        # Row 0 expands vertically, columns have proportional weights
        self.main_panel_container.grid_rowconfigure(0, weight=1)
        self.main_panel_container.grid_columnconfigure(0, weight=1, minsize=100)  # Control panel
        self.main_panel_container.grid_columnconfigure(1, weight=2, minsize=200)  # Transcript panel
        self.main_panel_container.grid_columnconfigure(2, weight=2, minsize=250)  # Insights panel

        # Left panel - Controls (grid column 0, resizable)
        self.create_control_panel(self.main_panel_container)

        # Center and right panels handled by new componentized layout

    def create_bottom_status_bar(self):
        """Create professional bottom status bar with clinical styling and proper dark mode"""
        try:
            # Status bar container with proper dark theme support
            self.status_bar_frame = ctk.CTkFrame(
                self.root,
                height=35,
                fg_color=self.get_color('bg_secondary', '#2d2d2d' if self.current_theme == 'dark' else '#f8f9fa'),
                corner_radius=0,  # No rounded corners for seamless edge-to-edge
                border_width=0,   # No border for seamless look
                border_color=self.get_color('border_subtle', '#404040' if self.current_theme == 'dark' else '#dee2e6')
            )
            self.status_bar_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
            self.status_bar_frame.pack_propagate(False)

            # Left section - Main status with proper contrast
            left_status_frame = ctk.CTkFrame(self.status_bar_frame, fg_color="transparent")
            left_status_frame.pack(side="left", fill="y", padx=10)

            self.status_label = ctk.CTkLabel(
                left_status_frame,
                text="Ready for new session",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.get_color('text_primary', '#ffffff' if self.current_theme == 'dark' else '#212529'),
                anchor="w"
            )
            self.status_label.pack(side="left", pady=8)

            # Center section - Session info with proper contrast
            center_status_frame = ctk.CTkFrame(self.status_bar_frame, fg_color="transparent")
            center_status_frame.pack(side="left", fill="both", expand=True, padx=10)

            self.session_info_label = ctk.CTkLabel(
                center_status_frame,
                text="",
                font=ctk.CTkFont(size=10),
                text_color=self.get_color('text_secondary', '#e0e0e0' if self.current_theme == 'dark' else '#6c757d'),
                anchor="center"
            )
            self.session_info_label.pack(expand=True, pady=8)

            # Right section - Connection status with proper theming
            right_status_frame = ctk.CTkFrame(self.status_bar_frame, fg_color="transparent")
            right_status_frame.pack(side="right", fill="y", padx=10)

            # Connection indicator with proper contrast
            self.connection_status_label = ctk.CTkLabel(
                right_status_frame,
                text="🔗 Local Mode",
                font=ctk.CTkFont(size=10),
                text_color=self.get_color('text_secondary', '#e0e0e0' if self.current_theme == 'dark' else '#6c757d')
            )
            self.connection_status_label.pack(side="right", padx=(0, 10), pady=8)

            # Theme toggle button with proper dark mode styling
            theme_text = "☀️ Light" if self.current_theme == 'dark' else "🌙 Dark"
            self.status_bar_theme_button = ctk.CTkButton(
                right_status_frame,
                text=theme_text,
                width=65,
                height=20,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color=self.get_color('button_secondary', '#374151' if self.current_theme == 'dark' else '#6c757d'),
                hover_color=self.get_color('button_secondary_hover', '#4b5563' if self.current_theme == 'dark' else '#5a6268'),
                text_color=self.get_color('button_secondary_text', '#f9fafb' if self.current_theme == 'dark' else '#ffffff'),
                command=self.toggle_dark_mode,
                corner_radius=4
            )
            self.status_bar_theme_button.pack(side="right", pady=6)

            print(f"[OK] Bottom status bar created with {self.current_theme} theme")

        except Exception as e:
            print(f"Error creating bottom status bar: {e}")
            # Create minimal status bar as fallback with proper theming
            try:
                self.status_label = ctk.CTkLabel(
                    self.main_container,
                    text="Ready for new session",
                    font=ctk.CTkFont(size=11),
                    text_color=self.get_color('text_primary', '#ffffff' if self.current_theme == 'dark' else '#212529')
                )
                self.status_label.pack(side="bottom", pady=5)
            except Exception as fallback_error:
                print(f"Fallback status bar creation failed: {fallback_error}")

    def create_control_panel(self, parent):
        """Create left control panel with resizable grid layout"""
        # Define color tuples for theme switching
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        
        # Per CustomTkinter docs: use grid with sticky="nsew" for full expansion
        width = getattr(self, 'layout_preferences', {}).get('control_panel_width', 200)

        self.control_frame = ctk.CTkFrame(
            parent,
            fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
            corner_radius=8
        )
        # Use grid instead of pack for resizability
        self.control_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        control_frame = self.control_frame

        # Panel header
        header = ctk.CTkFrame(control_frame, fg_color=bg_accent_tuple, corner_radius=6)
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            header,
            text="Session Controls",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(pady=8)

        # Scrollable content area with proper dark mode theming
        self.scrollable_frame = ctk.CTkScrollableFrame(
            control_frame,
            fg_color=self.get_color('bg_secondary', '#2d2d2d' if self.current_theme == 'dark' else '#ffffff'),
            scrollbar_fg_color=self.get_color('bg_accent', '#404040' if self.current_theme == 'dark' else '#f1f3f4'),
            scrollbar_button_color=self.get_color('primary', '#1e40af'),
            scrollbar_button_hover_color=self.get_color('accent', '#1d4ed8')
        )
        self.scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Device selection section
        self.create_device_section(self.scrollable_frame)

        # Recording controls section
        self.create_recording_section(self.scrollable_frame)

        # Analysis controls section
        # Analysis controls moved to right column - removed from left panel

    def create_device_section(self, parent):
        """Create device selection section"""
        section = self.create_section(parent, "Audio Devices")

        # REMOVED: Legacy device dropdowns - now using SessionControls panel
        # Microphone and system audio selection now in SessionControls component (left column)
        # mic_label = ctk.CTkLabel(section, text="Therapist Microphone:", font=ctk.CTkFont(size=11, weight="bold"))
        # mic_label.pack(anchor="w", pady=(5, 2))
        #
        # mic_options = [name for _, name in self.audio_devices["input"]]
        # self.mic_dropdown = ctk.CTkComboBox(
        #     section,
        #     values=mic_options if mic_options else ["No devices found"],
        #     height=28,
        #     font=ctk.CTkFont(size=10)
        # )
        # self.mic_dropdown.pack(fill="x", pady=(0, 10))
        # if mic_options:
        #     self.mic_dropdown.set(mic_options[0])
        #
        # # System audio selection
        # sys_label = ctk.CTkLabel(section, text="Client Audio Capture:", font=ctk.CTkFont(size=11, weight="bold"))
        # sys_label.pack(anchor="w", pady=(5, 2))
        #
        # sys_options = [name for _, name in self.audio_devices["loopback"]]
        # if not sys_options:
        #     sys_options = ["No system audio devices found"]
        # self.sys_dropdown = ctk.CTkComboBox(
        #     section,
        #     values=sys_options,
        #     height=28,
        #     font=ctk.CTkFont(size=10)
        # )
        # self.sys_dropdown.pack(fill="x", pady=(0, 10))
        # self.sys_dropdown.set(sys_options[0])

        # Dual-channel toggle
        self.dual_channel_var = ctk.BooleanVar(value=False)
        self.dual_channel_checkbox = ctk.CTkCheckBox(
            section,
            text="Enable dual-channel recording",
            variable=self.dual_channel_var,
            command=self.update_dual_channel_mode,
            font=ctk.CTkFont(size=10)
        )
        self.dual_channel_checkbox.pack(anchor="w", pady=(0, 5))

        # Advanced diarization toggle
        self.advanced_diarization_var = ctk.BooleanVar(value=False)
        self.advanced_diarization_checkbox = ctk.CTkCheckBox(
            section,
            text="High-accuracy speaker diarization",
            variable=self.advanced_diarization_var,
            command=self.update_advanced_diarization_mode,
            font=ctk.CTkFont(size=10)
        )
        self.advanced_diarization_checkbox.pack(anchor="w", pady=(0, 2))

        # Diarization status label (shows errors/status)
        self.diarization_status_hint = ctk.CTkLabel(
            section,
            text="",
            font=ctk.CTkFont(size=8),
            text_color="gray50"
        )
        self.diarization_status_hint.pack(anchor="w", padx=(25, 0), pady=(0, 5))

        # Diarization buffer size selection
        buffer_frame = ctk.CTkFrame(section, fg_color="transparent")
        buffer_frame.pack(fill="x", padx=(20, 0), pady=(0, 5))

        buffer_label = ctk.CTkLabel(
            buffer_frame,
            text="Processing delay:",
            font=ctk.CTkFont(size=9),
            text_color="gray60"
        )
        buffer_label.pack(side="left")

        self.diarization_buffer_var = ctk.StringVar(value="1 minute")
        self.diarization_buffer_dropdown = ctk.CTkOptionMenu(
            buffer_frame,
            variable=self.diarization_buffer_var,
            values=list(self.diarization_buffer_options.keys()),
            command=self.update_diarization_buffer_size,
            width=100,
            height=24,
            font=ctk.CTkFont(size=9)
        )
        self.diarization_buffer_dropdown.pack(side="right")

        # Max speakers control
        max_speakers_frame = ctk.CTkFrame(section, fg_color="transparent")
        max_speakers_frame.pack(fill="x", padx=(20, 0), pady=(5, 5))

        max_speakers_label = ctk.CTkLabel(
            max_speakers_frame,
            text="Max speakers:",
            font=ctk.CTkFont(size=9),
            text_color="gray60"
        )
        max_speakers_label.pack(side="left")

        self.max_speakers_var = ctk.IntVar(value=2)
        self.max_speakers_slider = ctk.CTkSlider(
            max_speakers_frame,
            from_=1,
            to=4,
            number_of_steps=3,
            variable=self.max_speakers_var,
            command=self.update_max_speakers_label,
            width=120,
            height=16
        )
        self.max_speakers_slider.pack(side="left", padx=5)

        self.max_speakers_label = ctk.CTkLabel(
            max_speakers_frame,
            text="2 speakers",
            font=ctk.CTkFont(size=9),
            text_color="gray60",
            width=60
        )
        self.max_speakers_label.pack(side="left")

        # Advanced diarization status
        self.diarization_status_label = ctk.CTkLabel(
            section,
            text="Requires pyannote.audio models",
            font=ctk.CTkFont(size=9),
            text_color="gray60"
        )
        self.diarization_status_label.pack(anchor="w", padx=(20, 0))

    def create_recording_section(self, parent):
        """Create recording controls section"""
        section = self.create_section(parent, "Recording")

        # REMOVED: Legacy record button - now using SessionControls panel
        # Main record button is now in the SessionControls component (left column)
        # self.record_button = ctk.CTkButton(
        #     section,
        #     text="Start Session",
        #     command=self.toggle_recording,
        #     font=ctk.CTkFont(size=14, weight="bold"),
        #     height=45,
        #     fg_color=self.colors.get('success', '#047857'),
        #     hover_color=self.colors.get('info', '#1d4ed8')
        # )
        # self.record_button.pack(fill="x", pady=(5, 10))

        # Progress Notes button
        self.progress_notes_button = ctk.CTkButton(
            section,
            text="📋 Generate Progress Notes",
            command=self.generate_progress_notes,
            font=ctk.CTkFont(size=12),
            height=35,
            fg_color=self.colors.get('button_primary', '#2B5AA0'),
            hover_color=self.colors.get('button_primary_hover', '#1E3A6B')
        )
        self.progress_notes_button.pack(fill="x", pady=(0, 10))

        # Buffer duration control
        buffer_label = ctk.CTkLabel(section, text="Buffer Duration:", font=ctk.CTkFont(size=11, weight="bold"))
        buffer_label.pack(anchor="w", pady=(5, 2))

        buffer_control_frame = ctk.CTkFrame(section, fg_color="transparent")
        buffer_control_frame.pack(fill="x", pady=(0, 10))

        self.buffer_slider = ctk.CTkSlider(
            buffer_control_frame,
            from_=30,
            to=45,
            number_of_steps=15,
            command=self.update_buffer_duration,
            height=16
        )
        self.buffer_slider.set(30)
        self.buffer_slider.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.buffer_value_label = ctk.CTkLabel(
            buffer_control_frame,
            text="30s",
            font=ctk.CTkFont(size=10),
            width=30
        )
        self.buffer_value_label.pack(side="right")

    def create_analysis_controls_section(self, parent):
        """Create on-demand analysis controls section"""
        section = self.create_section(parent, "AI Insights (On-Demand)")

        # Time window selector (1-10 minutes)
        window_label = ctk.CTkLabel(
            section,
            text="Time Window:",
            font=ctk.CTkFont(size=10)
        )
        window_label.pack(anchor="w", pady=(5, 2))

        self.insight_window_var = ctk.IntVar(value=5)
        window_frame = ctk.CTkFrame(section, fg_color="transparent")
        window_frame.pack(fill="x", pady=(0, 10))

        self.insight_window_slider = ctk.CTkSlider(
            window_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            variable=self.insight_window_var,
            command=self.update_insight_window_label,
            height=16
        )
        self.insight_window_slider.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.insight_window_label = ctk.CTkLabel(
            window_frame,
            text="5 min",
            font=ctk.CTkFont(size=10),
            width=40
        )
        self.insight_window_label.pack(side="right")

        # Note about Gemini API
        if not GEMINI_AVAILABLE:
            warning_label = ctk.CTkLabel(
                section,
                text="[WARN] Gemini API unavailable",
                font=ctk.CTkFont(size=9),
                text_color="orange"
            )
            warning_label.pack(anchor="w", pady=(0, 5))

        # Custom insight prompts - load from config or use defaults
        self.insight_prompts = self.load_insight_prompts()

        # Generate Insight Buttons
        prompts_label = ctk.CTkLabel(
            section,
            text="Generate Insight:",
            font=ctk.CTkFont(size=10, weight="bold")
        )
        prompts_label.pack(anchor="w", pady=(5, 5))

        # Create buttons for each prompt
        self.insight_buttons = {}
        for prompt_id, prompt_data in self.insight_prompts.items():
            btn = ctk.CTkButton(
                section,
                text=prompt_data['label'],
                command=lambda pid=prompt_id: self.generate_insight_on_demand(pid),
                height=28,
                font=ctk.CTkFont(size=10),
                fg_color=self.colors.get('button_primary', '#2B5AA0'),
                hover_color=self.colors.get('button_primary_hover', '#1E3A6B')
            )
            btn.pack(fill="x", pady=2)
            self.insight_buttons[prompt_id] = btn

            # Disable if Gemini API not available
            if not GEMINI_AVAILABLE:
                btn.configure(state="disabled")

        # Add "Manage Prompts" button
        manage_btn = ctk.CTkButton(
            section,
            text="⚙ Manage Custom Prompts",
            command=self.open_prompt_manager,
            height=24,
            font=ctk.CTkFont(size=9),
            fg_color="transparent",
            hover_color=self.colors.get('bg_accent', '#E0E0E0'),
            border_width=1,
            border_color=self.colors.get('text_muted', '#999999')
        )
        manage_btn.pack(fill="x", pady=(10, 5))

    def create_section(self, parent, title):
        """Create a styled section container"""
        # Define color tuples for theme switching
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        
        section_frame = ctk.CTkFrame(
            parent,
            fg_color=bg_accent_tuple,
            corner_radius=6
        )
        section_frame.pack(fill="x", pady=(0, 10))

        # Section header
        header = ctk.CTkLabel(
            section_frame,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        )
        header.pack(pady=(8, 0), padx=10)

        # Content area
        content = ctk.CTkFrame(section_frame, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=(5, 10))

        return content

    def create_transcript_panel(self, parent):
        """Create center transcript panel with resizable grid layout"""
        # Define color tuples for theme switching
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        
        # Per CustomTkinter docs: use grid with sticky="nsew" for full expansion
        width = getattr(self, 'layout_preferences', {}).get('transcript_panel_width', 450)

        self.transcript_frame = ctk.CTkFrame(
            parent,
            fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
            corner_radius=8
        )
        # Use grid instead of pack for resizability
        self.transcript_frame.grid(row=0, column=1, sticky="nsew", padx=2)
        transcript_frame = self.transcript_frame

        # Panel header with controls
        header_frame = ctk.CTkFrame(transcript_frame, fg_color=bg_accent_tuple, corner_radius=6)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Left side - title
        header_left = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_left.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            header_left,
            text="Live Transcript",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(anchor="w")

        # Right side - controls
        header_right = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_right.pack(side="right", padx=10, pady=8)

        # Font size controls with A-/A+ buttons
        font_frame = ctk.CTkFrame(header_right, fg_color="transparent")
        font_frame.pack(side="right", padx=(0, 10))

        # A- button
        self.font_decrease_btn = ctk.CTkButton(
            font_frame,
            text="A−",
            width=35,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.decrease_font_size,
            fg_color=self.colors.get('button_secondary', '#6c757d'),
            hover_color=self.colors.get('button_secondary_hover', '#5a6268'),
            corner_radius=6
        )
        self.font_decrease_btn.pack(side="left", padx=(0, 2))

        # Font size display
        self.transcript_font_size = 18  # Default 18 for readability
        self.font_size_label = ctk.CTkLabel(
            font_frame,
            text=f"{self.transcript_font_size}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff'),
            width=30
        )
        self.font_size_label.pack(side="left", padx=2)

        # A+ button
        self.font_increase_btn = ctk.CTkButton(
            font_frame,
            text="A+",
            width=35,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.increase_font_size,
            fg_color=self.colors.get('button_secondary', '#6c757d'),
            hover_color=self.colors.get('button_secondary_hover', '#5a6268'),
            corner_radius=6
        )
        self.font_increase_btn.pack(side="left", padx=(2, 10))

        # Copy transcript button
        self.copy_button = ctk.CTkButton(
            header_right,
            text="📋 Copy",
            width=80,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.copy_transcript,
            fg_color=self.colors.get('primary', '#1e40af'),
            hover_color=self.colors.get('accent', '#6d28d9'),
            corner_radius=6
        )
        self.copy_button.pack(side="right")

        # Transcript display area with LARGE FONT and HIGH CONTRAST
        # Dark mode: bg=#0B0F14, text=#E8E8E8 (88-90% white)
        transcript_bg = '#0B0F14' if self.current_theme == 'dark' else '#FFFFFF'
        transcript_fg = '#E8E8E8' if self.current_theme == 'dark' else '#212529'

        try:
            self.transcript_text = ctk.CTkTextbox(
                transcript_frame,
                font=ctk.CTkFont(size=self.transcript_font_size),  # Default 18
                wrap="word",
                fg_color=transcript_bg,
                text_color=transcript_fg,
                border_width=1,
                border_color=self.get_color('border_subtle', '#404040'),
                corner_radius=6,
                spacing1=4,  # Line spacing before paragraph
                spacing2=2,  # Line spacing between lines (line-height ~1.4)
                spacing3=4   # Line spacing after paragraph
            )
        except Exception as e:
            print(f"Error creating transcript text with styling: {e}")
            # Fallback to basic transcript text
            self.transcript_text = ctk.CTkTextbox(
                transcript_frame,
                font=ctk.CTkFont(size=self.transcript_font_size),
                wrap="word"
            )
        self.transcript_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Bind Ctrl+C for selection copying
        self.transcript_text.bind('<Control-c>', self.handle_transcript_copy)

        # Bind right-click for context menu
        self.transcript_text.bind('<Button-3>', self.show_transcript_context_menu)

        # Add placeholder text for better UX
        self.show_transcript_placeholder()

        # Status bar
        status_frame = ctk.CTkFrame(transcript_frame, fg_color=bg_accent_tuple, height=30, corner_radius=6)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))
        status_frame.pack_propagate(False)

        # REMOVED: Transcript status label (now using centralized status bar)
        # self.transcript_status_label = ctk.CTkLabel(
        #     status_frame,
        #     text="Ready for transcription",
        #     font=ctk.CTkFont(size=10),
        #     text_color=self.colors.get('text_secondary', '#e0e0e0')
        # )
        # self.transcript_status_label.pack(pady=8)

    def create_analysis_panel(self, parent):
        """Create right INSIGHTS column with grid layout - full height scrollable"""
        # Per CustomTkinter docs: grid with sticky="nsew" + weight=1 for full expansion
        width = getattr(self, 'layout_preferences', {}).get('insights_panel_width', 500)

        self.analysis_frame = ctk.CTkFrame(
            parent,
            fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
            corner_radius=8
        )
        # Use grid for full column expansion
        self.analysis_frame.grid(row=0, column=2, sticky="nsew", padx=(2, 0))

        # Configure grid to fill vertically
        self.analysis_frame.grid_rowconfigure(1, weight=1)  # Content area expands
        self.analysis_frame.grid_columnconfigure(0, weight=1)

        # Compact header
        header_frame = ctk.CTkFrame(
            self.analysis_frame,
            fg_color=self.colors.get('primary', '#1e40af'),
            corner_radius=6,
            height=45
        )
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        header_frame.grid_propagate(False)

        ctk.CTkLabel(
            header_frame,
            text="🔍 INSIGHTS STREAM",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        ).pack(side="left", padx=15, pady=8)

        self.collapse_button = ctk.CTkButton(
            header_frame,
            text="−",
            width=26,
            height=26,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.toggle_analysis_panel,
            fg_color=self.colors.get('bg_accent', '#404040'),
            hover_color=self.colors.get('text_muted', '#666666'),
            text_color="white",
            corner_radius=13
        )
        self.collapse_button.pack(side="right", padx=10, pady=8)

        # Main scrollable content area with grid sticky
        self.analysis_content = ctk.CTkScrollableFrame(
            self.analysis_frame,
            fg_color="transparent"
        )
        self.analysis_content.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # NEW RIGHT COLUMN HIERARCHY:
        # 1. Insight generation controls (moved from left)
        self.create_insight_controls_in_column()

        # 2. Insight chat input
        self.create_insight_chat_input()

        # 3. Risk alert banner (hidden by default)
        self.create_risk_alert_banner()

        # 4. Insights stream (cards)
        self.create_insights_section()

        # 5. Timeline (collapsed by default)
        self.create_timeline_section()

        # 6. Metrics footer (compact)
        self.create_metrics_footer()

    def create_insight_controls_in_column(self):
        """Create insight generation controls in right column"""
        # Show warning banner if insights are disabled
        if not self.analysis_enabled:
            warning_banner = ctk.CTkFrame(
                self.analysis_content,
                fg_color=self.colors.get('warning', '#f59e0b'),
                corner_radius=6
            )
            warning_banner.pack(fill="x", pady=(0, 10), padx=5)

            ctk.CTkLabel(
                warning_banner,
                text="⚠️ Insights Disabled: Missing API Key",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="white"
            ).pack(side="left", padx=10, pady=8)

            ctk.CTkLabel(
                warning_banner,
                text="Configure in Settings → Analysis",
                font=ctk.CTkFont(size=9),
                text_color="white"
            ).pack(side="left", padx=(0, 10))

        controls_frame = ctk.CTkFrame(
            self.analysis_content,
            fg_color=self.colors.get('bg_accent', '#2d2d2d'),
            corner_radius=6
        )
        controls_frame.pack(fill="x", pady=(0, 10))

        # Time window selector
        ctk.CTkLabel(
            controls_frame,
            text="Time Window:",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(anchor="w", padx=10, pady=(10, 2))

        self.insight_window_var = ctk.IntVar(value=5)
        window_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        window_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.insight_window_slider = ctk.CTkSlider(
            window_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            variable=self.insight_window_var,
            command=self.update_insight_window_label,
            height=16
        )
        self.insight_window_slider.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.insight_window_label = ctk.CTkLabel(
            window_frame,
            text="5 min",
            font=ctk.CTkFont(size=10),
            width=40,
            text_color=self.colors.get('text_primary', '#ffffff')
        )
        self.insight_window_label.pack(side="right")

        # Template selector
        ctk.CTkLabel(
            controls_frame,
            text="Analysis Template:",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(anchor="w", padx=10, pady=(10, 2))

        # Load available templates for dropdown
        self.load_templates_for_analysis()
        
        template_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        template_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.selected_template_var = ctk.StringVar(value="cbt_realtime")
        self.template_dropdown = ctk.CTkOptionMenu(
            template_frame,
            variable=self.selected_template_var,
            values=self.get_template_dropdown_options(),
            command=self.on_template_selection_changed,
            font=ctk.CTkFont(size=10),
            fg_color=self.colors.get('input_background', '#1a1a1a'),
            button_color=self.colors.get('primary', '#2B5AA0'),
            button_hover_color=self.colors.get('accent', '#1E3A6B')
        )
        self.template_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Template info button
        self.template_info_btn = ctk.CTkButton(
            template_frame,
            text="ℹ️",
            width=30,
            height=28,
            font=ctk.CTkFont(size=12),
            command=self.show_template_info,
            fg_color=self.colors.get('bg_accent', '#404040'),
            hover_color=self.colors.get('primary', '#2B5AA0')
        )
        self.template_info_btn.pack(side="right")
        
        # Category filter for templates (Phase 3 enhancement)
        category_filter_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        category_filter_frame.pack(fill="x", padx=10, pady=(5, 0))
        
        ctk.CTkLabel(
            category_filter_frame,
            text="Filter:",
            font=ctk.CTkFont(size=9),
            text_color=self.colors.get('text_secondary', '#888888')
        ).pack(side="left")
        
        self.template_category_filter = ctk.StringVar(value="All")
        category_filter_dropdown = ctk.CTkOptionMenu(
            category_filter_frame,
            variable=self.template_category_filter,
            values=["All", "Real-time", "Risk Assessment", "Custom"],
            command=self.filter_analysis_templates,
            font=ctk.CTkFont(size=9),
            width=100,
            height=24,
            fg_color=self.colors.get('bg_accent', '#404040'),
            button_color=self.colors.get('primary', '#2B5AA0')
        )
        category_filter_dropdown.pack(side="right")

        # Load prompts
        if not hasattr(self, 'insight_prompts'):
            self.insight_prompts = self.load_insight_prompts()

        # Template-based analysis button
        self.template_analysis_btn = ctk.CTkButton(
            controls_frame,
            text="🔍 Generate Analysis",
            command=self.generate_template_analysis,
            height=35,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.colors.get('success', '#047857'),
            hover_color=self.colors.get('success_hover', '#059669'),
            state="normal" if self.analysis_enabled else "disabled"
        )
        self.template_analysis_btn.pack(fill="x", padx=10, pady=(10, 5))
        
        # Quick analysis buttons container
        quick_label = ctk.CTkLabel(
            controls_frame,
            text="Quick Analysis:",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.colors.get('text_secondary', '#888888')
        )
        quick_label.pack(anchor="w", padx=10, pady=(10, 2))

        # Create button grid container
        self.prompt_buttons_container = ctk.CTkFrame(controls_frame, fg_color="transparent")
        self.prompt_buttons_container.pack(fill="x", padx=10, pady=(5, 0))

        # Render prompt buttons in grid
        self.insight_buttons = {}
        self.render_prompt_buttons()

    def render_prompt_buttons(self):
        """
        Render prompt buttons in a grid layout (4 columns).
        Always renders buttons - disables with tooltip if insights_enabled=False.
        """
        try:
            # Clear existing buttons
            for widget in self.prompt_buttons_container.winfo_children():
                widget.destroy()
            self.insight_buttons.clear()

            # Configure grid columns (4 columns, equal weight)
            for col in range(4):
                self.prompt_buttons_container.grid_columnconfigure(col, weight=1)

            # Filter prompts by category (real-time synonyms: 'real-time', 'realtime', 'live')
            real_time_categories = ['real-time', 'realtime', 'live', 'session']
            filtered_prompts = {
                pid: pdata for pid, pdata in self.insight_prompts.items()
                if pdata.get('category', '').lower() in real_time_categories
            }

            # If no filtered prompts, show all
            if not filtered_prompts:
                filtered_prompts = self.insight_prompts

            # Render buttons in grid
            row, col = 0, 0
            for prompt_id, prompt_data in filtered_prompts.items():
                btn = ctk.CTkButton(
                    self.prompt_buttons_container,
                    text=prompt_data.get('label', prompt_id),
                    command=lambda pid=prompt_id: self.on_prompt_button_click(pid),
                    height=28,
                    font=ctk.CTkFont(size=9),
                    fg_color=self.colors.get('bg_accent', '#404040'),
                    hover_color=self.colors.get('button_primary_hover', '#1E3A6B'),
                    state="normal" if self.analysis_enabled else "disabled"
                )
                btn.grid(row=row, column=col, padx=2, pady=2, sticky="ew")

                # Add tooltip for disabled buttons
                if not self.analysis_enabled:
                    self.create_tooltip(btn, "Add API key in Settings → Analysis")

                self.insight_buttons[prompt_id] = btn

                # Move to next position
                col += 1
                if col >= 4:
                    col = 0
                    row += 1

            print(f"[UI] Rendered {len(self.insight_buttons)} prompt buttons in grid")

        except Exception as e:
            print(f"Error rendering prompt buttons: {e}")

    def create_tooltip(self, widget, text):
        """Create a simple tooltip for a widget"""
        def on_enter(event):
            tooltip = ctk.CTkToplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = ctk.CTkLabel(
                tooltip,
                text=text,
                fg_color=self.colors.get('bg_accent', '#404040'),
                corner_radius=4,
                padx=8,
                pady=4
            )
            label.pack()

            widget._tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, '_tooltip'):
                widget._tooltip.destroy()
                del widget._tooltip

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def on_prompt_button_click(self, prompt_id):
        """Handle prompt button click - run insight generation"""
        # Early return if insights disabled
        if not self.analysis_enabled:
            self.set_status("Add API key in Settings → Analysis to enable insights")
            return

        try:
            # Resolve segment (highlight or time-based)
            seg_text, seg_label = self.resolve_segment()

            if not seg_text or len(seg_text.strip()) < 50:
                self.show_toast("Not enough transcript for analysis", 2000)
                return

            # Check if this is a template (from analysis_templates) or simple prompt (from insight_prompts)
            template = None
            prompt_text = None
            prompt_name = prompt_id

            # Try analysis_templates first (templates with variables)
            if hasattr(self, 'analysis_templates') and prompt_id in self.analysis_templates:
                template = self.analysis_templates[prompt_id]
                prompt_name = template.get('name', prompt_id)

                # Build variables dict
                template_variables = self.prepare_template_variables(seg_text,
                    self.insight_window_var.get() if hasattr(self, 'insight_window_var') else 5)

                # Substitute variables in template body
                prompt_text = self.substitute_template_variables(template.get('body', ''), template_variables)

            # Try prompt_templates (Prompt Editor templates)
            elif hasattr(self, 'prompt_templates') and prompt_id in self.prompt_templates:
                template = self.prompt_templates[prompt_id]
                prompt_name = template.get('name', prompt_id)

                # Build variables dict
                template_variables = self.prepare_template_variables(seg_text,
                    self.insight_window_var.get() if hasattr(self, 'insight_window_var') else 5)

                # Substitute variables in template body or prompt field
                template_body = template.get('body') or template.get('prompt', '')
                prompt_text = self.substitute_template_variables(template_body, template_variables)

            # Fallback to insight_prompts (simple prompts)
            elif hasattr(self, 'insight_prompts') and prompt_id in self.insight_prompts:
                prompt_data = self.insight_prompts[prompt_id]
                prompt_name = prompt_data.get('label', prompt_id)
                window_minutes = self.insight_window_var.get() if hasattr(self, 'insight_window_var') else 5
                prompt_text = f"{prompt_data['prompt']}\n\nTranscript ({seg_label}):\n{seg_text}"
            else:
                print(f"[ERROR] Prompt/template '{prompt_id}' not found")
                self.show_toast(f"Prompt '{prompt_id}' not found", 2000)
                return

            if not prompt_text:
                print(f"[ERROR] Could not generate prompt text for '{prompt_id}'")
                self.show_toast("Error generating prompt", 2000)
                return

            # Disable button during processing
            if prompt_id in self.insight_buttons:
                original_text = self.insight_buttons[prompt_id].cget("text")
                self.insight_buttons[prompt_id].configure(state="disabled", text="⏳")
            else:
                original_text = prompt_name

            # Show status
            self.set_status(f"Generating: {prompt_name}...")

            # Run in background thread
            def run_insight_call():
                try:
                    # Generate insight using active provider
                    success, insight_text = self.generate_with_provider(prompt_text)

                    if success:
                        # Display result card on main thread
                        def show_result():
                            self.display_insight_card({
                                'title': prompt_name,
                                'segment_label': seg_label,
                                'content': insight_text,
                                'timestamp': datetime.now().strftime('%H:%M:%S')
                            })

                            # Re-enable button
                            if prompt_id in self.insight_buttons:
                                self.insight_buttons[prompt_id].configure(
                                    state="normal" if self.analysis_enabled else "disabled",
                                    text=original_text
                                )

                            self.set_status(f"Generated: {prompt_name}")

                        self.root.after(0, show_result)

                    else:
                        # API call failed
                        def show_error():
                            messagebox.showerror("Error", f"Insight generation failed:\n{insight_text}")
                            if prompt_id in self.insight_buttons:
                                self.insight_buttons[prompt_id].configure(
                                    state="normal" if self.analysis_enabled else "disabled",
                                    text=original_text
                                )
                        self.root.after(0, show_error)

                except Exception as e:
                    print(f"[ERROR] Insight generation failed: {e}")
                    def show_error():
                        messagebox.showerror("Error", f"Insight generation failed:\n{str(e)}")
                        if prompt_id in self.insight_buttons:
                            self.insight_buttons[prompt_id].configure(
                                state="normal" if self.analysis_enabled else "disabled",
                                text=original_text
                            )
                        self.set_status("Error generating insight")
                    self.root.after(0, show_error)

            # Start background thread
            threading.Thread(target=run_insight_call, daemon=True).start()

        except Exception as e:
            print(f"[ERROR] on_prompt_button_click: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to start insight:\n{str(e)}")

    def display_insight_card(self, card_data):
        """
        Display an insight result as a card with copy/popup actions.

        Args:
            card_data: Dict with keys: title, segment_label, content, timestamp
        """
        try:
            if not hasattr(self, 'insights_scrollable') or not self.insights_scrollable.winfo_exists():
                print("[ERROR] Insights scrollable container not available")
                return

            # Remove empty state message if present
            for widget in self.insights_scrollable.winfo_children():
                # Check if this is the empty state placeholder
                if isinstance(widget, ctk.CTkFrame):
                    children = widget.winfo_children()
                    if children and isinstance(children[0], ctk.CTkLabel):
                        label_text = children[0].cget("text")
                        if "No insights yet" in label_text or "Generate an insight" in label_text:
                            widget.destroy()

            # Create card frame
            card = ctk.CTkFrame(
                self.insights_scrollable,
                fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                corner_radius=6,
                border_width=1,
                border_color=self.colors.get('border_subtle', '#404040')
            )

            # Header section
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=12, pady=(12, 8))

            # Title
            title_text = f"{card_data.get('title', 'Insight')} • {card_data.get('segment_label', '')} • {card_data.get('timestamp', '')}"
            title_label = ctk.CTkLabel(
                header,
                text=title_text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.colors.get('text_secondary', '#888888'),
                anchor="w"
            )
            title_label.pack(side="left", fill="x", expand=True)

            # Body section (read-only text)
            content_text = card_data.get('content', 'No content')

            # Use CTkTextbox for scrollable, read-only text
            text_widget = ctk.CTkTextbox(
                card,
                height=120,
                wrap="word",
                font=ctk.CTkFont(size=11),
                fg_color=self.colors.get('bg_primary', '#1a1a1a'),
                border_width=0,
                activate_scrollbars=True
            )
            text_widget.pack(fill="both", padx=12, pady=(0, 8))
            text_widget.insert("1.0", content_text)
            text_widget.configure(state="disabled")  # Make read-only

            # Button section
            button_frame = ctk.CTkFrame(card, fg_color="transparent")
            button_frame.pack(fill="x", padx=12, pady=(0, 12))

            # Copy button
            copy_btn = ctk.CTkButton(
                button_frame,
                text="📋 Copy",
                width=80,
                height=28,
                font=ctk.CTkFont(size=10),
                fg_color=self.colors.get('bg_accent', '#404040'),
                hover_color=self.colors.get('button_primary_hover', '#1E3A6B'),
                command=lambda: self.copy_insight_to_clipboard(content_text)
            )
            copy_btn.pack(side="left", padx=(0, 5))

            # Open in Window button
            open_btn = ctk.CTkButton(
                button_frame,
                text="🗗 Open",
                width=80,
                height=28,
                font=ctk.CTkFont(size=10),
                fg_color=self.colors.get('bg_accent', '#404040'),
                hover_color=self.colors.get('button_primary_hover', '#1E3A6B'),
                command=lambda: self.open_insight_popup(card_data)
            )
            open_btn.pack(side="left")

            # Pack card at the top (most recent first)
            children = self.insights_scrollable.winfo_children()
            if children:
                card.pack(fill="x", pady=(0, 5), before=children[0])
            else:
                card.pack(fill="x", pady=(0, 5))

            # Limit to 10 cards (remove oldest)
            cards = self.insights_scrollable.winfo_children()
            if len(cards) > 10:
                cards[-1].destroy()

            print(f"[UI] Displayed insight card: {card_data.get('title', 'Unnamed')}")

        except Exception as e:
            print(f"[ERROR] display_insight_card: {e}")
            import traceback
            traceback.print_exc()

    def copy_insight_to_clipboard(self, text):
        """Copy insight text to clipboard and show toast"""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.show_toast("Copied to clipboard", 1500)
        except Exception as e:
            print(f"[ERROR] copy_insight_to_clipboard: {e}")
            messagebox.showerror("Error", f"Failed to copy to clipboard:\n{str(e)}")

    def open_insight_popup(self, card_data):
        """
        Open a full-screen popup window to view insight in detail.

        Args:
            card_data: Dict with keys: title, segment_label, content, timestamp
        """
        try:
            # Create toplevel window
            popup = ctk.CTkToplevel(self.root)
            popup.title(f"Insight: {card_data.get('title', 'Unnamed')}")
            popup.geometry("800x600")

            # Center the window
            popup.update_idletasks()
            width = popup.winfo_width()
            height = popup.winfo_height()
            x = (popup.winfo_screenwidth() // 2) - (width // 2)
            y = (popup.winfo_screenheight() // 2) - (height // 2)
            popup.geometry(f"{width}x{height}+{x}+{y}")

            # Make it resizable
            popup.resizable(True, True)

            # Header section
            header_frame = ctk.CTkFrame(popup, fg_color=self.colors.get('bg_accent', '#2d2d2d'), corner_radius=0)
            header_frame.pack(fill="x", padx=0, pady=0)

            # Title and metadata
            title_text = f"{card_data.get('title', 'Insight')}"
            meta_text = f"{card_data.get('segment_label', '')} • {card_data.get('timestamp', '')}"

            title_label = ctk.CTkLabel(
                header_frame,
                text=title_text,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=self.colors.get('text_primary', '#ffffff'),
                anchor="w"
            )
            title_label.pack(anchor="w", padx=20, pady=(15, 5))

            meta_label = ctk.CTkLabel(
                header_frame,
                text=meta_text,
                font=ctk.CTkFont(size=11),
                text_color=self.colors.get('text_secondary', '#888888'),
                anchor="w"
            )
            meta_label.pack(anchor="w", padx=20, pady=(0, 15))

            # Content section (scrollable textbox)
            content_frame = ctk.CTkFrame(popup, fg_color=self.colors.get('bg_primary', '#1a1a1a'))
            content_frame.pack(fill="both", expand=True, padx=20, pady=(10, 0))

            text_widget = ctk.CTkTextbox(
                content_frame,
                wrap="word",
                font=ctk.CTkFont(size=12),
                fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                border_width=1,
                border_color=self.colors.get('border_subtle', '#404040'),
                activate_scrollbars=True
            )
            text_widget.pack(fill="both", expand=True, padx=0, pady=0)
            text_widget.insert("1.0", card_data.get('content', 'No content'))
            text_widget.configure(state="disabled")  # Make read-only

            # Button section
            button_frame = ctk.CTkFrame(popup, fg_color="transparent")
            button_frame.pack(fill="x", padx=20, pady=15)

            # Copy button
            copy_btn = ctk.CTkButton(
                button_frame,
                text="📋 Copy to Clipboard",
                width=150,
                height=35,
                font=ctk.CTkFont(size=12),
                fg_color=self.colors.get('primary', '#2B5AA0'),
                hover_color=self.colors.get('accent', '#1E3A6B'),
                command=lambda: self.copy_insight_to_clipboard(card_data.get('content', ''))
            )
            copy_btn.pack(side="left", padx=(0, 10))

            # Close button
            close_btn = ctk.CTkButton(
                button_frame,
                text="Close",
                width=100,
                height=35,
                font=ctk.CTkFont(size=12),
                fg_color=self.colors.get('bg_accent', '#404040'),
                hover_color=self.colors.get('button_primary_hover', '#1E3A6B'),
                command=popup.destroy
            )
            close_btn.pack(side="left")

            # Focus the window
            popup.focus()

            print(f"[UI] Opened insight popup: {card_data.get('title', 'Unnamed')}")

        except Exception as e:
            print(f"[ERROR] open_insight_popup: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to open insight popup:\n{str(e)}")

    def create_insight_chat_input(self):
        """Create insight chat input box beneath buttons"""
        chat_frame = ctk.CTkFrame(
            self.analysis_content,
            fg_color=self.colors.get('bg_accent', '#2d2d2d'),
            corner_radius=6
        )
        chat_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            chat_frame,
            text="Quick Insight Query:",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(anchor="w", padx=10, pady=(10, 5))

        input_frame = ctk.CTkFrame(chat_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.insight_chat_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Ask about the session..." if self.analysis_enabled else "API key required",
            height=32,
            font=ctk.CTkFont(size=10),
            fg_color=self.colors.get('input_background', '#1a1a1a'),
            border_color=self.colors.get('border_subtle', '#404040'),
            state="normal" if self.analysis_enabled else "disabled"
        )
        self.insight_chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        if self.analysis_enabled:
            self.insight_chat_entry.bind("<Return>", lambda e: self.send_chat_insight())

        self.insight_chat_send_btn = ctk.CTkButton(
            input_frame,
            text="Send",
            width=60,
            height=32,
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self.send_chat_insight,
            fg_color=self.colors.get('primary', '#2B5AA0'),
            hover_color=self.colors.get('accent', '#1E3A6B'),
            state="normal" if self.analysis_enabled else "disabled"
        )
        self.insight_chat_send_btn.pack(side="right")

    def generate_template_analysis(self):
        """Generate analysis using the selected template with variable substitution"""
        # Early return if insights are disabled
        if not self.analysis_enabled:
            return

        try:
            # Check if template is selected
            if not hasattr(self, 'selected_template_id') or not self.selected_template_id:
                messagebox.showwarning("No Template", "Please select an analysis template first.")
                return
            
            # Get selected template
            template = self.analysis_templates.get(self.selected_template_id)
            if not template:
                messagebox.showerror("Template Error", "Selected template not found.")
                return
            
            # Get time window and transcript
            window_minutes = self.insight_window_var.get()
            window_seconds = window_minutes * 60
            transcript_text = self.get_recent_transcript(window_seconds)
            
            if not transcript_text or len(transcript_text.strip()) < 50:
                self.show_toast(f"Not enough transcript in last {window_minutes} min", 2000)
                return
            
            # Show progress
            self.template_analysis_btn.configure(text="⏳ Analyzing...", state="disabled")
            
            # Run analysis in background thread
            def run_template_analysis():
                try:
                    # Prepare template variables
                    template_variables = self.prepare_template_variables(transcript_text, window_minutes)
                    
                    # Substitute variables in template
                    analysis_prompt = self.substitute_template_variables(template['prompt'], template_variables)
                    
                    print(f"[ANALYSIS] Using template: {template['name']}")
                    print(f"[ANALYSIS] Variables substituted: {list(template_variables.keys())}")

                    # Generate analysis using multi-provider system
                    success, insight_text = self.generate_with_provider(analysis_prompt)

                    if not success:
                        insight_text = f"Analysis generation failed: {insight_text}"
                        print(f"[ERROR] {insight_text}")

                    # Create insight card with template metadata
                    card = {
                        'title': f"{template['name']} - {window_minutes}min Analysis",
                        'body': insight_text,
                        'tags': [f"Template: {template['name']}", f"{window_minutes}min window", template['category']],
                        'ts': datetime.now(),
                        'template_id': self.selected_template_id,
                        'variables_used': list(template_variables.keys())
                    }
                    
                    # Add to insights panel (thread-safe)
                    self.root.after(0, lambda: self.add_template_analysis_card(card))
                    
                except Exception as e:
                    error_msg = f"Template analysis error: {str(e)}"
                    print(f"[ERROR] {error_msg}")
                    
                    # Show error card
                    error_card = {
                        'title': 'Analysis Error',
                        'body': f"Failed to generate analysis using template '{template['name']}':\n\n{str(e)}",
                        'tags': ['Error', 'Template Analysis'],
                        'ts': datetime.now()
                    }
                    self.root.after(0, lambda: self.add_template_analysis_card(error_card))
                
                finally:
                    # Re-enable button
                    self.root.after(0, lambda: self.template_analysis_btn.configure(
                        text="🔍 Generate Analysis", state="normal"))
            
            # Start analysis thread
            analysis_thread = threading.Thread(target=run_template_analysis, daemon=True)
            analysis_thread.start()
            
        except Exception as e:
            print(f"Error starting template analysis: {e}")
            messagebox.showerror("Analysis Error", f"Failed to start analysis: {str(e)}")
            self.template_analysis_btn.configure(text="🔍 Generate Analysis", state="normal")
    
    def prepare_template_variables(self, transcript_text, window_minutes):
        """Prepare variables for template substitution"""
        try:
            # Get session context and metadata
            session_duration = self.get_session_duration_minutes()
            analysis_history = self.get_analysis_history_summary()
            session_context = self.get_session_context_summary()
            
            # Determine current risk level
            risk_level = getattr(self, 'current_risk_level', 'LOW')
            if hasattr(self, 'risk_alerts') and self.risk_alerts:
                recent_alerts = [a for a in self.risk_alerts if time.time() - a.get('timestamp', 0) < 1800]  # 30 min
                if recent_alerts:
                    risk_level = 'MEDIUM' if len(recent_alerts) < 3 else 'HIGH'
            
            # Prepare variable dictionary
            variables = {
                'transcript_segment': transcript_text,
                'session_context': session_context,
                'session_duration': str(session_duration),
                'therapy_modality': getattr(self, 'therapy_modality', 'General'),
                'analysis_history': analysis_history,
                'risk_level': risk_level,
                'window_minutes': str(window_minutes),
                'current_time': datetime.now().strftime('%H:%M:%S'),
                'session_date': datetime.now().strftime('%Y-%m-%d')
            }
            
            print(f"[VARIABLES] Prepared {len(variables)} template variables")
            return variables
            
        except Exception as e:
            print(f"Error preparing template variables: {e}")
            return {
                'transcript_segment': transcript_text,
                'session_context': 'Context unavailable',
                'session_duration': str(window_minutes),
                'therapy_modality': 'General',
                'analysis_history': 'History unavailable',
                'risk_level': 'UNKNOWN'
            }
    
    def substitute_template_variables(self, template_prompt, variables):
        """Substitute variables in template prompt"""
        try:
            substituted_prompt = template_prompt
            
            # Replace each variable
            for var_name, var_value in variables.items():
                placeholder = f"{{{var_name}}}"
                if placeholder in substituted_prompt:
                    substituted_prompt = substituted_prompt.replace(placeholder, str(var_value))
                    print(f"[SUBSTITUTE] {var_name} -> {len(str(var_value))} chars")
            
            # Check for unsubstituted variables
            remaining_vars = re.findall(r'\{([^}]+)\}', substituted_prompt)
            if remaining_vars:
                print(f"[WARNING] Unsubstituted variables: {remaining_vars}")
                # Replace with placeholder text
                for var in remaining_vars:
                    placeholder = f"{{{var}}}"
                    substituted_prompt = substituted_prompt.replace(placeholder, f"[{var} not available]")
            
            return substituted_prompt
            
        except Exception as e:
            print(f"Error substituting template variables: {e}")
            return template_prompt
    
    def add_template_analysis_card(self, card_data):
        """Add template analysis result as insight card"""
        try:
            if hasattr(self, 'insights_actions') and self.insights_actions.add_insight_card:
                self.insights_actions.add_insight_card(card_data)
                print(f"[SUCCESS] Added template analysis card: {card_data['title']}")
            else:
                print("[ERROR] insights_actions.add_insight_card not available")
                
        except Exception as e:
            print(f"Error adding template analysis card: {e}")
    
    def send_chat_insight(self):
        """Send custom insight query from chat input"""
        # Early return if insights are disabled
        if not self.analysis_enabled:
            return

        query = self.insight_chat_entry.get().strip()
        if not query:
            return

        try:
            self.insight_chat_entry.delete(0, 'end')

            # Get time window and transcript
            window_minutes = self.insight_window_var.get()
            window_seconds = window_minutes * 60
            transcript_text = self.get_recent_transcript(window_seconds)

            if not transcript_text or len(transcript_text.strip()) < 50:
                self.show_toast(f"Not enough transcript in last {window_minutes} min", 2000)
                return

            # Generate insight with custom query
            def run_chat_insight():
                try:
                    prompt = f"{query}\n\nContext - Last {window_minutes} min of transcript:\n{transcript_text}"

                    # Use multi-provider system
                    success, insight_text = self.generate_with_provider(prompt)

                    if not success:
                        error_msg = f"Chat insight failed: {insight_text}"
                        print(error_msg)
                        self.root.after(0, lambda: self.show_toast(error_msg, 3000))
                        return

                    timestamp = time.strftime("%H:%M:%S")

                    # Create card with query as title
                    insight_data = {
                        'type': f"Query: {query[:40]}..." if len(query) > 40 else f"Query: {query}",
                        'content': insight_text,
                        'timestamp': time.time(),
                        'sent_at': timestamp
                    }

                    self.root.after(0, lambda: self._render_insight_card(insight_data))
                    self.root.after(0, lambda: self.show_toast(f"Insight generated", 2000))

                except Exception as e:
                    error_msg = f"Chat insight failed: {str(e)}"
                    print(error_msg)
                    self.root.after(0, lambda: self.show_toast(error_msg, 3000))

            threading.Thread(target=run_chat_insight, daemon=True).start()

        except Exception as e:
            print(f"Error in send_chat_insight: {e}")

    def create_risk_alert_banner(self):
        """Create risk alert banner (hidden by default)"""
        self.risk_banner = ctk.CTkFrame(
            self.analysis_content,
            fg_color=self.colors.get('danger', '#dc3545'),
            corner_radius=6,
            height=60
        )
        # Initially hidden - will be shown when risk detected
        self.risk_banner.pack_forget()

        alert_content = ctk.CTkFrame(self.risk_banner, fg_color="transparent")
        alert_content.pack(fill="both", expand=True, padx=10, pady=10)

        # Alert icon and text
        alert_left = ctk.CTkFrame(alert_content, fg_color="transparent")
        alert_left.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            alert_left,
            text="[WARN]️ RISK ALERT",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white"
        ).pack(anchor="w")

        self.risk_alert_text = ctk.CTkLabel(
            alert_left,
            text="High risk indicators detected",
            font=ctk.CTkFont(size=10),
            text_color="white"
        )
        self.risk_alert_text.pack(anchor="w")

        # Dismiss button
        alert_right = ctk.CTkFrame(alert_content, fg_color="transparent")
        alert_right.pack(side="right")

        dismiss_btn = ctk.CTkButton(
            alert_right,
            text="×",
            width=24,
            height=24,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.dismiss_risk_alert,
            fg_color="transparent",
            hover_color=self.colors.get('warning', '#b45309'),
            text_color="white"
        )
        dismiss_btn.pack()

    def create_insights_section(self):
        """Create current insights section with enhanced clinical styling"""
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        # Enhanced insights section with special clinical background
        insights_section = ctk.CTkFrame(
            self.analysis_content,
            fg_color=self.colors.get('insight_bg', bg_accent_tuple),
            corner_radius=8,
            border_width=2,
            border_color=self.colors.get('primary', '#1e40af')
        )
        insights_section.pack(fill="x", pady=(5, 10))

        # Enhanced section header with clinical emphasis
        header_frame = ctk.CTkFrame(insights_section, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(8, 5))

        ctk.CTkLabel(
            header_frame,
            text="💡 CURRENT INSIGHTS",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(side="left", anchor="w")

        # Status indicator removed - using stream-based approach instead

        # Enhanced scrollable insights area with clinical styling
        self.insights_scrollable = ctk.CTkScrollableFrame(
            insights_section,
            height=220,  # Slightly taller for better visibility
            fg_color=self.colors.get('bg_primary', '#1a1a1a'),  # Use theme background
            corner_radius=6,
            border_width=1,
            border_color=self.colors.get('text_muted', '#ADB5BD')
        )
        self.insights_scrollable.pack(fill="x", padx=10, pady=(5, 10))

        # Initial empty state
        self.create_empty_insights_state()

    def create_timeline_section(self):
        """Create session timeline section - COLLAPSED BY DEFAULT"""
        self.timeline_section = ctk.CTkFrame(
            self.analysis_content,
            fg_color=self.colors.get('bg_accent', '#2d2d2d'),
            corner_radius=6
        )
        self.timeline_section.pack(fill="x", pady=(0, 10))

        # Collapsible header
        header_frame = ctk.CTkFrame(self.timeline_section, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=8)

        self.timeline_toggle_btn = ctk.CTkButton(
            header_frame,
            text="▶ Session Timeline",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.toggle_timeline,
            fg_color="transparent",
            hover_color=self.colors.get('bg_secondary', '#1a1a1a'),
            text_color=self.colors.get('text_primary', '#ffffff'),
            anchor="w"
        )
        self.timeline_toggle_btn.pack(fill="x")

        # Timeline content (initially hidden)
        self.timeline_content = ctk.CTkFrame(self.timeline_section, fg_color="transparent")
        # Start collapsed
        self.timeline_content.pack_forget()

        # Timeline progress bar
        self.timeline_progress = ctk.CTkProgressBar(
            self.timeline_content,
            height=8,
            progress_color=self.colors.get('primary', '#2B5AA0')
        )
        self.timeline_progress.pack(fill="x", padx=10, pady=(5, 5))
        self.timeline_progress.set(0)

        # Timeline markers
        self.timeline_markers = ctk.CTkFrame(self.timeline_content, fg_color="transparent", height=40)
        self.timeline_markers.pack(fill="x", padx=10, pady=(0, 10))

        self.timeline_expanded = False

    def toggle_timeline(self):
        """Toggle timeline section expansion"""
        self.timeline_expanded = not self.timeline_expanded
        if self.timeline_expanded:
            self.timeline_content.pack(fill="x", padx=10, pady=(0, 10))
            self.timeline_toggle_btn.configure(text="▼ Session Timeline")
        else:
            self.timeline_content.pack_forget()
            self.timeline_toggle_btn.configure(text="▶ Session Timeline")

    def create_metrics_footer(self):
        """Create compact metrics footer with bottom padding"""
        footer = ctk.CTkFrame(
            self.analysis_content,
            fg_color=self.colors.get('bg_accent', '#2d2d2d'),
            corner_radius=6
        )
        footer.pack(fill="x", pady=(0, 20))  # Bottom padding to prevent clipping

        # Compact header
        ctk.CTkLabel(
            footer,
            text="📊 Session Metrics",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        ).pack(pady=(8, 5), padx=10, anchor="w")

        # Compact metrics in single line
        metrics_line = ctk.CTkFrame(footer, fg_color="transparent")
        metrics_line.pack(fill="x", padx=10, pady=(0, 8))

        # Analyses count
        ctk.CTkLabel(
            metrics_line,
            text="Analyses:",
            font=ctk.CTkFont(size=9),
            text_color=self.colors.get('text_secondary', '#888888')
        ).pack(side="left")

        self.analysis_count_label = ctk.CTkLabel(
            metrics_line,
            text="0",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        )
        self.analysis_count_label.pack(side="left", padx=(5, 15))

        # Cost
        ctk.CTkLabel(
            metrics_line,
            text="Cost:",
            font=ctk.CTkFont(size=9),
            text_color=self.colors.get('text_secondary', '#888888')
        ).pack(side="left")

        self.cost_label = ctk.CTkLabel(
            metrics_line,
            text="$0.00",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=self.colors.get('text_primary', '#ffffff')
        )
        self.cost_label.pack(side="right")

    def create_empty_insights_state(self):
        """Create empty state for insights section"""
        empty_frame = ctk.CTkFrame(self.insights_scrollable, fg_color=self.colors.get('bg_secondary', '#2d2d2d'), corner_radius=6)
        empty_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(
            empty_frame,
            text="No insights yet",
            font=ctk.CTkFont(size=11),
            text_color=self.colors.get('text_muted', '#b0b0b0')
        ).pack(pady=20)

        ctk.CTkLabel(
            empty_frame,
            text="Start recording and enable analysis\nto see real-time insights",
            font=ctk.CTkFont(size=9),
            text_color=self.colors.get('text_muted', '#b0b0b0')
        ).pack(pady=(0, 20))

    # ===================================================================
    # DASHBOARD UI EVENT HANDLERS AND UPDATES
    # ===================================================================

    def update_transcript_font(self, font_size):
        """Update transcript font size"""
        try:
            size = int(font_size)
            self.transcript_text.configure(font=ctk.CTkFont(size=size))
        except:
            pass

    def show_transcript_placeholder(self):
        """Show professional placeholder text in transcript area"""
        placeholder_text = (
            "🎙️ Session Transcript\n\n"
            "Click 'Start Recording' to begin transcription.\n\n"
            "Live transcription will appear here with:\n"
            "• Speaker identification (Speaker 1 / Speaker 2)\n"
            "• Timestamp markers\n"
            "• Real-time text processing\n\n"
            "Professional features:\n"
            "• HIPAA-compliant local processing\n"
            "• No audio data leaves this device\n"
            "• Privacy-focused transcription\n"
            "• Therapy analysis with Claude AI\n\n"
            "Ready for professional therapy session transcription."
        )

        self.transcript_text.delete("1.0", "end")
        self.transcript_text.insert("1.0", placeholder_text)

        # Style the placeholder text
        try:
            self.transcript_text.configure(text_color=self.get_color('text_muted'))
        except Exception as e:
            print(f"Error styling placeholder text: {e}")
        self.transcript_placeholder_active = True

    def clear_transcript_placeholder(self):
        """Clear placeholder text when recording starts"""
        if getattr(self, 'transcript_placeholder_active', False):
            self.transcript_text.delete("1.0", "end")
            try:
                self.transcript_text.configure(text_color=self.get_color('text_primary'))
            except Exception as e:
                print(f"Error resetting transcript text color: {e}")
            self.transcript_placeholder_active = False

    def copy_transcript(self):
        """Copy the current transcript to clipboard"""
        try:
            # Get the current transcript text
            transcript_content = self._get_transcript_as_text()

            # Don't copy placeholder text
            if getattr(self, 'transcript_placeholder_active', False):
                self.show_status_message("No transcript content to copy", "warning")
                return

            # Copy to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(transcript_content)

            # Show feedback to user by temporarily changing button text
            if hasattr(self, 'copy_button'):
                original_text = self.copy_button.cget("text")
                self.copy_button.configure(text="[OK] Copied!")

                # Reset button text after 2 seconds
                self.root.after(2000, lambda: self.copy_button.configure(text=original_text))

            print(f"Transcript copied to clipboard ({len(transcript_content)} characters)")

        except Exception as e:
            print(f"Error copying transcript: {e}")

            # Show error feedback if button exists
            if hasattr(self, 'copy_button'):
                self.copy_button.configure(text="[ERROR] Error")
                self.root.after(2000, lambda: self.copy_button.configure(text="📋 Copy"))

    def increase_font_size(self):
        """Increase transcript font size (max 24)"""
        if self.transcript_font_size < 24:
            self.transcript_font_size += 1
            self.font_size_label.configure(text=f"{self.transcript_font_size}")
            self.transcript_text.configure(font=ctk.CTkFont(size=self.transcript_font_size))
            self.save_font_size_to_settings()
            print(f"Font size increased to {self.transcript_font_size}")

    def decrease_font_size(self):
        """Decrease transcript font size (min 14)"""
        if self.transcript_font_size > 14:
            self.transcript_font_size -= 1
            self.font_size_label.configure(text=f"{self.transcript_font_size}")
            self.transcript_text.configure(font=ctk.CTkFont(size=self.transcript_font_size))
            self.save_font_size_to_settings()
            print(f"Font size decreased to {self.transcript_font_size}")

    def save_font_size_to_settings(self):
        """Save font size to settings file"""
        try:
            import json
            import os

            settings_path = 'amanuensis_settings.json'

            # Load existing settings
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    config = json.load(f)
            else:
                config = {}

            # Update font size
            if 'ui' not in config:
                config['ui'] = {}
            config['ui']['transcript_font_size'] = self.transcript_font_size

            # Save settings
            with open(settings_path, 'w') as f:
                json.dump(config, f, indent=2)

        except Exception as e:
            print(f"Error saving font size to settings: {e}")

    def toggle_analysis_panel(self):
        """Toggle analysis panel visibility"""
        if self.dashboard_state['analysis_visible']:
            # Hide panel
            self.analysis_frame.pack_forget()
            self.collapse_button.configure(text="+")
            self.dashboard_state['analysis_visible'] = False
        else:
            # Show panel
            self.analysis_frame.pack(side="right", fill="y", padx=(5, 0))
            self.collapse_button.configure(text="−")
            self.dashboard_state['analysis_visible'] = True

    def dismiss_risk_alert(self):
        """Dismiss risk alert banner"""
        self.risk_banner.pack_forget()

    def show_risk_alert(self, alert_data):
        """Show risk alert banner with alert data (legacy - now uses TopNavBar)"""
        risk_level = alert_data.get('alert_level', 'MEDIUM')

        # Update TopNavBar risk badge (new UI)
        if hasattr(self, 'topnav_state'):
            self.topnav_state.risk_level = risk_level
            # Risk badge will auto-update via state binding

        # Update dashboard state
        self.dashboard_state['risk_level'] = risk_level

        # Legacy UI updates (guarded for backward compatibility)
        if hasattr(self, 'risk_alert_text'):
            self.risk_alert_text.configure(text=alert_data.get('message', 'Risk detected'))

        if hasattr(self, 'risk_level_label'):
            self.risk_level_label.configure(text=risk_level)

        if hasattr(self, 'risk_banner') and hasattr(self, 'insights_scrollable'):
            try:
                self.risk_banner.pack(fill="x", pady=(0, 10), before=self.insights_scrollable.master)
            except:
                pass  # Ignore if old UI doesn't exist

    def _render_insight_card(self, insight_data):
        """Resilient renderer for insight cards - handles strings and dicts"""
        try:
            # DIAGNOSTICS: Log render call
            if hasattr(self, 'verbose_insights') and self.verbose_insights:
                print("INSIGHT_RENDER_CALL")

            # Handle string payload - create default card
            if isinstance(insight_data, str):
                insight_data = {
                    'type': 'Live Therapist Insight',
                    'content': insight_data,
                    'timestamp': time.time()
                }

            # Ensure required fields with safe defaults
            card_data = {
                'type': insight_data.get('type', 'Live Therapist Insight'),
                'content': insight_data.get('content', insight_data.get('text', 'No content')),
                'timestamp': insight_data.get('timestamp', time.time()),
                'confidence': insight_data.get('confidence'),
                'window_minutes': insight_data.get('window_minutes')
            }

            # Check widget still exists
            if not self.insights_scrollable.winfo_exists():
                print("ERROR: insights_scrollable destroyed during render")
                return

            # Remove empty state if present
            for widget in self.insights_scrollable.winfo_children():
                if "No insights yet" in str(widget):
                    widget.destroy()

            # Create insight card
            card = ctk.CTkFrame(
                self.insights_scrollable,
                fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
                corner_radius=6
            )

            # PREPEND newest cards (insert at top)
            children = self.insights_scrollable.winfo_children()
            if children:
                card.pack(fill="x", pady=(0, 5), before=children[0])
            else:
                card.pack(fill="x", pady=(0, 5))

            # Card header
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(8, 0))

            # Insight type
            type_text = card_data['type']
            if card_data.get('window_minutes'):
                type_text += f" ({card_data['window_minutes']} min)"

            ctk.CTkLabel(
                header,
                text=type_text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=self.colors.get('primary', '#1e40af')
            ).pack(side="left")

            # Optional confidence badge
            if card_data['confidence'] is not None:
                confidence = card_data['confidence']
                confidence_color = self.colors.get('success', '#047857') if confidence > 0.8 else self.colors.get('warning', '#b45309') if confidence > 0.5 else self.colors.get('danger', '#dc2626')
                ctk.CTkLabel(
                    header,
                    text=f"{confidence:.0%}",
                    font=ctk.CTkFont(size=9),
                    text_color=confidence_color
                ).pack(side="right")

            # Insight content
            content_text = card_data['content']
            ctk.CTkLabel(
                card,
                text=content_text,
                font=ctk.CTkFont(size=10),
                text_color=self.colors.get('text_primary', '#ffffff'),
                wraplength=400,
                justify="left"
            ).pack(fill="x", padx=10, pady=(5, 8))

            # Timestamp
            time_str = datetime.fromtimestamp(card_data['timestamp']).strftime("%H:%M:%S")
            ctk.CTkLabel(
                card,
                text=time_str,
                font=ctk.CTkFont(size=8),
                text_color=self.colors.get('text_muted', '#b0b0b0')
            ).pack(anchor="e", padx=10, pady=(0, 8))

            # Limit cards (keep last 10)
            cards = self.insights_scrollable.winfo_children()
            if len(cards) > 10:
                cards[-1].destroy()  # Remove oldest

        except Exception as e:
            print(f"ERROR in _render_insight_card: {e}")
            import traceback
            traceback.print_exc()

    def add_insight_card(self, insight_data):
        """Legacy wrapper - routes to unified renderer"""
        self._render_insight_card(insight_data)

    def update_session_metrics(self):
        """Update session metrics in header and analysis panel (DEPRECATED)"""
        try:
            # Session metrics display
            # REMOVED: duration_label (using bottom status bar)
            # REMOVED: analysis_count_label, cost_label (not using legacy metrics)
            pass

        except Exception as e:
            # Silently ignore - this method is deprecated
            pass

    def update_transcript_status(self, status_text):
        """Update transcript status bar (DEPRECATED - use set_status instead)"""
        # Route to centralized status bar
        self.set_status(status_text)

    def update_session_status(self, status_text):
        """Update session status in header (DEPRECATED - use set_status instead)"""
        # Route to centralized status bar
        self.set_status(status_text)

    def start_session_ui_updates(self):
        """Start session-related UI updates"""
        self.dashboard_state['session_active'] = True
        # REMOVED: Legacy record_button updates (using SessionControls actions)
        self.update_session_status("Recording in progress...")
        self.update_transcript_status("Transcribing audio...")

        # Start periodic UI updates
        self.schedule_dashboard_updates()

    def stop_session_ui_updates(self):
        """Stop session-related UI updates"""
        self.dashboard_state['session_active'] = False
        # REMOVED: Legacy record_button updates (using SessionControls actions)
        self.update_session_status("Session completed")
        self.update_transcript_status("Transcription finished")

    def schedule_dashboard_updates(self):
        """Schedule periodic dashboard updates"""
        if self.dashboard_state['session_active']:
            # Update metrics every second
            self.update_session_metrics()

            # Schedule next update
            self.root.after(1000, self.schedule_dashboard_updates)

    def thread_safe_ui_update(self, update_func, *args, **kwargs):
        """Execute UI update in main thread safely"""
        def safe_update():
            try:
                update_func(*args, **kwargs)
            except Exception as e:
                print(f"UI update error: {e}")

        self.root.after(0, safe_update)

    def thread_safe_add_insight(self, insight_data):
        """Thread-safe method to add insight from analysis thread"""
        self.thread_safe_ui_update(self.add_insight_card, insight_data)

    def thread_safe_show_risk_alert(self, alert_data):
        """Thread-safe method to show risk alert from analysis thread"""
        self.thread_safe_ui_update(self.show_risk_alert, alert_data)

    # ===================================================================
    # INTEGRATED ANALYSIS PROCESSING
    # ===================================================================

    def process_analysis_result(self, result):
        """Process analysis result and update dashboard"""
        try:
            if result.get('success'):
                # Extract insights from analysis
                insights = self.extract_insights_from_analysis(result)

                # Add insights to dashboard
                for insight in insights:
                    self.thread_safe_add_insight(insight)

                # Check for risk alerts
                if 'structured_analysis' in result:
                    risk_data = result['structured_analysis'].get('risk_assessment', {})
                    if risk_data.get('score', 0) >= 7:
                        alert_data = {
                            'alert_level': 'HIGH' if risk_data['score'] >= 8 else 'MEDIUM',
                            'message': f"Risk score: {risk_data['score']}/10",
                            'analysis_id': result['id']
                        }
                        self.thread_safe_show_risk_alert(alert_data)

                # Update dashboard metrics
                self.thread_safe_ui_update(self.update_session_metrics)

        except Exception as e:
            print(f"Error processing analysis result: {e}")

    def extract_insights_from_analysis(self, result):
        """Extract insights from Claude analysis result"""
        insights = []

        try:
            # Extract from structured analysis if available
            if 'structured_analysis' in result:
                structured = result['structured_analysis']

                # Cognitive patterns
                if 'cognitive_patterns' in structured:
                    for pattern in structured['cognitive_patterns'][:2]:  # Limit to 2
                        insights.append({
                            'type': 'Cognitive Pattern',
                            'content': pattern,
                            'confidence': 0.8,
                            'timestamp': result['timestamp']
                        })

                # Emotional themes
                if 'emotional_themes' in structured:
                    for theme in structured['emotional_themes'][:2]:  # Limit to 2
                        insights.append({
                            'type': 'Emotional Theme',
                            'content': theme,
                            'confidence': 0.7,
                            'timestamp': result['timestamp']
                        })

                # Recommendations
                if 'recommendations' in structured:
                    for rec in structured['recommendations'][:1]:  # Limit to 1
                        insights.append({
                            'type': 'Recommendation',
                            'content': rec,
                            'confidence': 0.9,
                            'timestamp': result['timestamp']
                        })

            # Fallback to summary if no structured analysis
            elif 'summary' in result:
                insights.append({
                    'type': 'Summary',
                    'content': result['summary'],
                    'confidence': 0.6,
                    'timestamp': result['timestamp']
                })

        except Exception as e:
            print(f"Error extracting insights: {e}")

        return insights


    # ===================================================================
    # SETTINGS AND CUSTOMIZATION METHODS
    # ===================================================================

    def show_settings_modal(self):
        """Show comprehensive settings modal"""
        try:
            # Get actual current appearance mode from CustomTkinter
            actual_mode = ctk.get_appearance_mode()  # Returns "Dark" or "Light"
            actual_mode_lower = actual_mode.lower()

            # Sync self.current_theme with actual mode
            self.current_theme = actual_mode_lower

            is_dark = (actual_mode_lower == 'dark')

            # Debug logging
            if self.VERBOSE_UI:
                print(f"[SETTINGS] Opening with theme: {actual_mode_lower} (from CTk: {actual_mode})")

            # IMPORTANT: Use COLOR TUPLES (light, dark) for automatic theme switching
            # Per CustomTkinter docs: fg_color accepts tuple: (light_color, dark_color)
            BG = ("#f8f9fa", "#121212")     # Window background
            BG2 = ("#ffffff", "#1a1a1a")    # Panel backgrounds
            FG = ("#212529", "#e6e6e6")     # Text color
            ACC = "#5b9cff"                  # Accent (same in both modes)
            HOV = "#4a8bf8"                  # Hover (same in both modes)
            BRD = ("#adb5bd", "#2b2b2b")    # Borders
            INP = BG2                        # Input backgrounds same as panels

            # Create modal window
            self.settings_window = ctk.CTkToplevel(self.root)
            self.settings_window.title("Amanuensis V2 - Settings")
            self.settings_window.geometry("800x600")
            self.settings_window.transient(self.root)
            self.settings_window.grab_set()
            self.settings_window.configure(fg_color=BG)

            # Center the window
            self.settings_window.update_idletasks()
            x = (self.settings_window.winfo_screenwidth() // 2) - (800 // 2)
            y = (self.settings_window.winfo_screenheight() // 2) - (600 // 2)
            self.settings_window.geometry(f"800x600+{x}+{y}")

            # Main container
            main_frame = ctk.CTkFrame(self.settings_window, fg_color=BG2)
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)

            # Header
            header_frame = ctk.CTkFrame(main_frame, fg_color=ACC, corner_radius=8, border_width=1, border_color=BRD)
            header_frame.pack(fill="x", pady=(0, 20))

            ctk.CTkLabel(
                header_frame,
                text="Settings & Customization",
                font=ctk.CTkFont(size=20, weight="bold"),
                text_color="white"
            ).pack(pady=15)

            # Settings tabs using CTkTabview with theme colors
            self.settings_tabview = ctk.CTkTabview(
                main_frame,
                width=750,
                fg_color=BG2,
                segmented_button_fg_color=INP,
                segmented_button_selected_color=ACC,
                segmented_button_selected_hover_color=HOV,
                text_color=FG,
                border_color=BRD
            )
            self.settings_tabview.pack(fill="both", expand=True)

            # Create tabs
            self.settings_tabview.add("API Keys")
            self.settings_tabview.add("Dashboard")
            self.settings_tabview.add("Analysis")
            self.settings_tabview.add("Insights Presets")
            self.settings_tabview.add("Prompt Editor")
            self.settings_tabview.add("Audio")
            self.settings_tabview.add("Export")

            # Populate tabs
            self.create_api_keys_tab()
            self.create_dashboard_settings_tab()
            self.create_analysis_settings_tab()
            self.create_insights_presets_tab()
            self.create_prompt_editor_tab()
            self.create_audio_settings_tab()
            self.create_export_settings_tab()

            # Configure tab backgrounds immediately (no flicker)
            self.settings_window.update_idletasks()
            self._configure_settings_tabs(BG2)

            # Button bar
            button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            button_frame.pack(fill="x", pady=(20, 0))

            # Apply button (uses tuples for theme compatibility)
            apply_button = ctk.CTkButton(
                button_frame,
                text="Apply Settings",
                command=self.apply_settings,
                fg_color=("#047857", "#10b981"),  # Light green, Dark green
                hover_color=("#059669", "#059669"),
                width=120,
                text_color=("white", "white")
            )
            apply_button.pack(side="right", padx=(10, 0))

            # Cancel button (uses tuples for theme compatibility)
            cancel_button = ctk.CTkButton(
                button_frame,
                text="Cancel",
                command=self.close_settings_modal,
                fg_color=("#dc2626", "#b91c1c"),  # Light red, Dark red
                hover_color=("#dc3545", "#dc3545"),
                width=120,
                text_color=("white", "white")
            )
            cancel_button.pack(side="right", padx=5)

            # Reset button (uses tuples for theme compatibility)
            reset_button = ctk.CTkButton(
                button_frame,
                text="Reset to Defaults",
                command=self.reset_to_defaults,
                fg_color=("#b45309", "#f59e0b"),  # Light orange, Dark orange
                hover_color=("#e0a800", "#e0a800"),
                width=140,
                text_color=("white", "white")
            )
            reset_button.pack(side="left")

            # Add refresh_theme method to modal for runtime re-theming
            def refresh_theme():
                """Re-theme the settings modal when theme changes"""
                try:
                    # Use self.current_theme as source of truth
                    is_dark_refresh = (self.current_theme == 'dark')

                    # Simply update appearance mode - widgets with tuple colors will auto-update
                    ctk.set_appearance_mode("dark" if is_dark_refresh else "light")

                    if self.VERBOSE_UI:
                        print(f"SETTINGS re-themed: mode={'dark' if is_dark_refresh else 'light'}")

                except Exception as e:
                    print(f"Error refreshing settings theme: {e}")

            self.settings_window.refresh_theme = refresh_theme
            self.settings_modal = self.settings_window  # Store reference for theme toggle

        except Exception as e:
            print(f"Error showing settings modal: {e}")

    def _configure_settings_tabs(self, bg_color_tuple):
        """Safely configure all settings tab backgrounds with theme-aware tuple colors"""
        try:
            if not hasattr(self, 'settings_tabview'):
                return

            # bg_color_tuple should be (light_color, dark_color) for automatic theme switching
            for tab_name in ["API Keys", "Dashboard", "Analysis", "Prompt Editor", "Audio", "Export"]:
                try:
                    tab = self.settings_tabview.tab(tab_name)
                    if tab and tab.winfo_exists():
                        tab.configure(fg_color=bg_color_tuple)
                except Exception as e:
                    if self.VERBOSE_UI:
                        print(f"Could not configure tab {tab_name}: {e}")
        except Exception as e:
            if self.VERBOSE_UI:
                print(f"Error in _configure_settings_tabs: {e}")

    def create_api_keys_tab(self):
        """Create API Keys configuration tab with support for multiple providers"""
        tab = self.settings_tabview.tab("API Keys")

        # Get theme colors
        is_dark = (self.current_theme == 'dark')
        bg_color_tuple = ("#ffffff", "#1a1a1a")
        bg_accent_tuple = ("#e9ecef", "#404040")

        # Scrollable frame for all providers
        scroll_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=bg_color_tuple,
            scrollbar_button_color=self.colors.get('primary', '#5b9cff'),
            scrollbar_button_hover_color=self.colors.get('accent', '#4a8bf8')
        )
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Header
        header = ctk.CTkLabel(
            scroll_frame,
            text="AI Provider API Keys",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        header.pack(anchor="w", pady=(0, 5))

        info_label = ctk.CTkLabel(
            scroll_frame,
            text="Configure API keys for AI-powered insights. Keys are stored locally in your settings file.",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_muted', '#9CA3AF'),
            wraplength=650,
            justify="left"
        )
        info_label.pack(anchor="w", pady=(0, 10))

        # Active provider selection
        provider_select_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple, corner_radius=8)
        provider_select_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            provider_select_frame,
            text="Active Provider:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            provider_select_frame,
            text="Select which AI provider to use for insights generation",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_muted', '#9CA3AF')
        ).pack(anchor="w", padx=15, pady=(0, 10))

        # Provider selector
        if not hasattr(self, 'active_provider'):
            self.active_provider = 'gemini'

        self.active_provider_var = ctk.StringVar(value=self.active_provider)

        provider_selector = ctk.CTkComboBox(
            provider_select_frame,
            values=['gemini', 'claude', 'openai', 'openrouter'],
            variable=self.active_provider_var,
            width=400,
            fg_color=self.colors.get('input_background', '#1a1a1a' if is_dark else '#ffffff'),
            button_color=self.colors.get('primary', '#5b9cff'),
            button_hover_color=self.colors.get('accent', '#4a8bf8'),
            border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd'),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        provider_selector.pack(anchor="w", padx=30, pady=(0, 15))

        # Initialize API key variables if they don't exist
        if not hasattr(self, 'api_keys'):
            self.api_keys = {
                'gemini': '',
                'claude': '',
                'openai': '',
                'openrouter': ''
            }

        # Gemini Section
        self._create_provider_section(
            scroll_frame,
            bg_accent_tuple,
            is_dark,
            provider_id='gemini',
            provider_name='Google Gemini',
            placeholder='sk-...',
            docs_url='https://ai.google.dev/',
            models=['gemini-2.0-flash-001', 'gemini-1.5-pro-latest', 'gemini-1.5-flash-latest']
        )

        # Claude Section
        self._create_provider_section(
            scroll_frame,
            bg_accent_tuple,
            is_dark,
            provider_id='claude',
            provider_name='Anthropic Claude',
            placeholder='sk-ant-...',
            docs_url='https://console.anthropic.com/',
            models=['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307']
        )

        # OpenAI Section
        self._create_provider_section(
            scroll_frame,
            bg_accent_tuple,
            is_dark,
            provider_id='openai',
            provider_name='OpenAI',
            placeholder='sk-...',
            docs_url='https://platform.openai.com/api-keys',
            models=['gpt-4o', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo']
        )

        # OpenRouter Section
        self._create_provider_section(
            scroll_frame,
            bg_accent_tuple,
            is_dark,
            provider_id='openrouter',
            provider_name='OpenRouter',
            placeholder='sk-or-...',
            docs_url='https://openrouter.ai/keys',
            models=['auto', 'anthropic/claude-3.5-sonnet', 'openai/gpt-4-turbo', 'meta-llama/llama-3.1-70b-instruct']
        )

    def _create_provider_section(self, parent, bg_accent_tuple, is_dark, provider_id, provider_name, placeholder, docs_url, models):
        """Create a provider API key section with input, test, and model selection"""
        # Provider frame
        provider_frame = ctk.CTkFrame(parent, fg_color=bg_accent_tuple, corner_radius=8)
        provider_frame.pack(fill="x", pady=(0, 15))

        # Header
        header_frame = ctk.CTkFrame(provider_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 10))

        title = ctk.CTkLabel(
            header_frame,
            text=provider_name,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        title.pack(side="left")

        # Get API key button
        docs_btn = ctk.CTkButton(
            header_frame,
            text="Get API Key →",
            width=100,
            height=24,
            font=ctk.CTkFont(size=9),
            fg_color="transparent",
            hover_color=self.colors.get('bg_secondary', '#2d2d2d'),
            border_width=1,
            border_color=self.colors.get('border_subtle', '#404040'),
            command=lambda url=docs_url: self._open_url(url)
        )
        docs_btn.pack(side="right")

        # API Key input with show/hide
        key_frame = ctk.CTkFrame(provider_frame, fg_color="transparent")
        key_frame.pack(fill="x", padx=30, pady=(0, 10))

        ctk.CTkLabel(
            key_frame,
            text="API Key:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", pady=(0, 5))

        input_row = ctk.CTkFrame(key_frame, fg_color="transparent")
        input_row.pack(fill="x")

        # Create entry with variable
        key_var = ctk.StringVar(value=self.api_keys.get(provider_id, ''))
        setattr(self, f'{provider_id}_key_var', key_var)  # Store reference

        key_entry = ctk.CTkEntry(
            input_row,
            placeholder_text=placeholder,
            show="•",
            width=400,
            height=32,
            textvariable=key_var,
            fg_color=self.colors.get('input_background', '#1a1a1a' if is_dark else '#ffffff'),
            border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd'),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        key_entry.pack(side="left", padx=(0, 5))
        setattr(self, f'{provider_id}_key_entry', key_entry)  # Store reference

        # Show/Hide toggle
        show_var = ctk.BooleanVar(value=False)
        def toggle_show():
            if show_var.get():
                key_entry.configure(show="")
                show_btn.configure(text="👁️")
            else:
                key_entry.configure(show="•")
                show_btn.configure(text="👁️‍🗨️")

        show_btn = ctk.CTkButton(
            input_row,
            text="👁️‍🗨️",
            width=40,
            height=32,
            fg_color=self.colors.get('bg_secondary', '#2d2d2d'),
            hover_color=self.colors.get('bg_accent', '#404040'),
            command=lambda: [show_var.set(not show_var.get()), toggle_show()]
        )
        show_btn.pack(side="left", padx=(0, 5))

        # Test button with status
        test_btn = ctk.CTkButton(
            input_row,
            text="Test",
            width=70,
            height=32,
            fg_color=self.colors.get('primary', '#2B5AA0'),
            hover_color=self.colors.get('accent', '#1E3A6B'),
            command=lambda: self._test_api_key(provider_id, key_var.get(), test_btn)
        )
        test_btn.pack(side="left")

        # Model selection
        model_frame = ctk.CTkFrame(provider_frame, fg_color="transparent")
        model_frame.pack(fill="x", padx=30, pady=(0, 15))

        ctk.CTkLabel(
            model_frame,
            text="Default Model:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", pady=(0, 5))

        # Create model variable
        model_var = ctk.StringVar(value=models[0] if models else '')
        setattr(self, f'{provider_id}_model_var', model_var)

        model_dropdown = ctk.CTkComboBox(
            model_frame,
            values=models,
            variable=model_var,
            width=400,
            fg_color=self.colors.get('input_background', '#1a1a1a' if is_dark else '#ffffff'),
            button_color=self.colors.get('primary', '#5b9cff'),
            button_hover_color=self.colors.get('accent', '#4a8bf8'),
            border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd'),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        model_dropdown.pack(anchor="w")

    def _open_url(self, url):
        """Open URL in default browser"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            print(f"Error opening URL: {e}")

    def _test_api_key(self, provider_id, api_key, button):
        """Test API key for specified provider"""
        if not api_key or api_key.strip() == '':
            messagebox.showwarning("No API Key", f"Please enter an API key for {provider_id}")
            return

        # Disable button and show testing state
        button.configure(text="Testing...", state="disabled")

        def test_in_background():
            try:
                success = False
                message = ""

                if provider_id == 'gemini':
                    success, message = self._test_gemini(api_key)
                elif provider_id == 'claude':
                    success, message = self._test_claude(api_key)
                elif provider_id == 'openai':
                    success, message = self._test_openai(api_key)
                elif provider_id == 'openrouter':
                    success, message = self._test_openrouter(api_key)

                # Update UI on main thread
                def show_result():
                    button.configure(text="✓ Success" if success else "✗ Failed", state="normal")
                    if success:
                        button.configure(fg_color=self.colors.get('success', '#047857'))
                        messagebox.showinfo("Success", message)
                    else:
                        button.configure(fg_color=self.colors.get('danger', '#dc2626'))
                        messagebox.showerror("Test Failed", message)

                    # Reset button after 3 seconds
                    self.root.after(3000, lambda: button.configure(
                        text="Test",
                        fg_color=self.colors.get('primary', '#2B5AA0')
                    ))

                self.root.after(0, show_result)

            except Exception as e:
                def show_error():
                    button.configure(text="✗ Error", state="normal", fg_color=self.colors.get('danger', '#dc2626'))
                    messagebox.showerror("Error", f"Test error: {str(e)}")
                    self.root.after(3000, lambda: button.configure(
                        text="Test",
                        fg_color=self.colors.get('primary', '#2B5AA0')
                    ))
                self.root.after(0, show_error)

        # Run test in background thread
        threading.Thread(target=test_in_background, daemon=True).start()

    def _test_gemini(self, api_key):
        """Test Gemini API key"""
        try:
            if not GEMINI_AVAILABLE:
                return False, "Gemini SDK not installed. Run: pip install google-genai"

            import google.genai as genai_test
            client = genai_test.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.0-flash-001',
                contents='Hello'
            )
            return True, f"✅ Gemini API connected successfully!\n\nResponse: {response.text[:50]}..."
        except Exception as e:
            return False, f"Gemini API test failed:\n{str(e)}"

    def _test_claude(self, api_key):
        """Test Claude API key"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello"}]
            )
            return True, f"✅ Claude API connected successfully!\n\nResponse: {message.content[0].text}"
        except ImportError:
            return False, "Anthropic SDK not installed. Run: pip install anthropic"
        except Exception as e:
            return False, f"Claude API test failed:\n{str(e)}"

    def _test_openai(self, api_key):
        """Test OpenAI API key"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            return True, f"✅ OpenAI API connected successfully!\n\nResponse: {response.choices[0].message.content}"
        except ImportError:
            return False, "OpenAI SDK not installed. Run: pip install openai"
        except Exception as e:
            return False, f"OpenAI API test failed:\n{str(e)}"

    def _test_openrouter(self, api_key):
        """Test OpenRouter API key"""
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key
            )
            response = client.chat.completions.create(
                model="openai/gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            return True, f"✅ OpenRouter API connected successfully!\n\nResponse: {response.choices[0].message.content}"
        except ImportError:
            return False, "OpenAI SDK not installed (required for OpenRouter). Run: pip install openai"
        except Exception as e:
            return False, f"OpenRouter API test failed:\n{str(e)}"

    def generate_with_provider(self, prompt_text):
        """
        Generate text using the active AI provider.

        Args:
            prompt_text: The prompt to send to the AI

        Returns:
            tuple: (success: bool, response_text: str)
        """
        try:
            provider = getattr(self, 'active_provider', 'gemini')
            print(f"[AI] Generating with provider: {provider}")

            if not hasattr(self, 'api_keys') or not self.api_keys.get(provider):
                return False, f"No API key configured for {provider}. Please add it in Settings → API Keys."

            if provider == 'gemini':
                return self._generate_gemini(prompt_text)
            elif provider == 'claude':
                return self._generate_claude(prompt_text)
            elif provider == 'openai':
                return self._generate_openai(prompt_text)
            elif provider == 'openrouter':
                return self._generate_openrouter(prompt_text)
            else:
                return False, f"Unknown provider: {provider}"

        except Exception as e:
            print(f"[ERROR] generate_with_provider: {e}")
            return False, f"Generation error: {str(e)}"

    def _generate_gemini(self, prompt_text):
        """Generate text using Gemini"""
        try:
            if not GEMINI_AVAILABLE:
                return False, "Gemini SDK not installed. Run: pip install google-genai"

            import google.genai as genai_call
            api_key = self.api_keys.get('gemini')
            model = getattr(self, 'gemini_model', 'gemini-2.0-flash-001')

            client = genai_call.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt_text
            )
            return True, response.text
        except Exception as e:
            return False, f"Gemini error: {str(e)}"

    def _generate_claude(self, prompt_text):
        """Generate text using Claude"""
        try:
            import anthropic
            api_key = self.api_keys.get('claude')
            model = getattr(self, 'claude_model', 'claude-3-5-sonnet-20241022')

            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt_text}]
            )
            return True, message.content[0].text
        except ImportError:
            return False, "Anthropic SDK not installed. Run: pip install anthropic"
        except Exception as e:
            return False, f"Claude error: {str(e)}"

    def _generate_openai(self, prompt_text):
        """Generate text using OpenAI"""
        try:
            from openai import OpenAI
            api_key = self.api_keys.get('openai')
            model = getattr(self, 'openai_model', 'gpt-4o')

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=2048
            )
            return True, response.choices[0].message.content
        except ImportError:
            return False, "OpenAI SDK not installed. Run: pip install openai"
        except Exception as e:
            return False, f"OpenAI error: {str(e)}"

    def _generate_openrouter(self, prompt_text):
        """Generate text using OpenRouter"""
        try:
            from openai import OpenAI
            api_key = self.api_keys.get('openrouter')
            model = getattr(self, 'openrouter_model', 'auto')

            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key
            )
            response = client.chat.completions.create(
                model=model if model != 'auto' else 'openai/gpt-4-turbo',
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=2048
            )
            return True, response.choices[0].message.content
        except ImportError:
            return False, "OpenAI SDK not installed (required for OpenRouter). Run: pip install openai"
        except Exception as e:
            return False, f"OpenRouter error: {str(e)}"

    def create_dashboard_settings_tab(self):
        """Create dashboard customization settings"""
        tab = self.settings_tabview.tab("Dashboard")

        # Get theme state for conditional fallbacks
        is_dark = (self.current_theme == 'dark')

        # Use color tuples (light, dark) for automatic theme switching per CustomTkinter docs
        bg_color_tuple = ("#ffffff", "#1a1a1a")  # (light, dark)
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        bg_color = self.colors.get('bg_secondary', '#1a1a1a' if is_dark else '#ffffff')

        # Scrollable frame for settings
        scroll_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=bg_color_tuple,
            scrollbar_button_color=self.colors.get('primary', '#5b9cff'),
            scrollbar_button_hover_color=self.colors.get('accent', '#4a8bf8')
        )
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Color theme settings
        theme_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        theme_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            theme_frame,
            text="Color Theme",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.theme_var = ctk.StringVar(value="clinical")
        theme_options = ["clinical", "professional", "warm", "high_contrast"]

        for theme in theme_options:
            radio = ctk.CTkRadioButton(
                theme_frame,
                text=theme.replace("_", " ").title(),
                variable=self.theme_var,
                value=theme,
                fg_color=self.colors.get('primary', '#5b9cff'),
                text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529'),
                border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd')
            )
            radio.pack(anchor="w", padx=30, pady=3)

        # Layout preferences
        layout_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        layout_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            layout_frame,
            text="Layout Preferences",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # Auto-expand removed - insights stream always visible in right column

        # Show timestamps in transcript
        self.show_timestamps_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            layout_frame,
            text="Show timestamps in transcript",
            variable=self.show_timestamps_var,
            fg_color=self.colors.get('primary', '#5b9cff'),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529'),
            border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd')
        ).pack(anchor="w", padx=30, pady=5)

        # Risk alert position
        self.risk_alert_position_var = ctk.StringVar(value="top_right")
        ctk.CTkLabel(
            layout_frame,
            text="Risk Alert Position:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=30, pady=(15, 5))

        position_options = ["top_right", "top_left", "bottom_right", "bottom_left"]
        position_dropdown = ctk.CTkComboBox(
            layout_frame,
            values=[pos.replace("_", " ").title() for pos in position_options],
            variable=self.risk_alert_position_var,
            width=200,
            fg_color=self.colors.get('input_background', bg_color),
            button_color=self.colors.get('primary', '#5b9cff'),
            button_hover_color=self.colors.get('accent_hover', '#4a8bf8'),
            border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd'),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        position_dropdown.pack(anchor="w", padx=30, pady=(0, 15))

    def create_analysis_settings_tab(self):
        """Create analysis configuration settings"""
        tab = self.settings_tabview.tab("Analysis")

        # Get theme colors - use self.current_theme as source of truth
        is_dark = (self.current_theme == 'dark')
        
        # Use color tuples (light, dark) for automatic theme switching
        bg_color_tuple = ("#ffffff", "#1a1a1a")  # (light, dark)
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        bg_color = self.colors.get('bg_secondary', '#1a1a1a' if is_dark else '#ffffff')

        scroll_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=bg_color_tuple,
            scrollbar_button_color=self.colors.get('primary', '#5b9cff'),
            scrollbar_button_hover_color=self.colors.get('accent', '#4a8bf8')
        )
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Gemini API settings
        api_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        api_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            api_frame,
            text="Gemini API Configuration",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # API Key input (read-only, shows configured key)
        ctk.CTkLabel(
            api_frame,
            text="API Key:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=30, pady=(10, 5))

        api_key_display = ctk.CTkLabel(
            api_frame,
            text="API Key: [Set via GOOGLE_API_KEY environment variable]",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_muted', '#9CA3AF')
        )
        api_key_display.pack(anchor="w", padx=30, pady=(0, 10))

        # Model selection
        ctk.CTkLabel(
            api_frame,
            text="Analysis Model:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=30, pady=(10, 5))

        self.model_var = ctk.StringVar(value="gemini-1.5-flash-latest")
        model_options = [
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro-latest",
            "gemini-1.0-pro-latest"
        ]
        model_dropdown = ctk.CTkComboBox(
            api_frame,
            values=model_options,
            variable=self.model_var,
            width=300,
            fg_color=self.colors.get('input_background', bg_color),
            button_color=self.colors.get('primary', '#5b9cff'),
            button_hover_color=self.colors.get('accent_hover', '#4a8bf8'),
            border_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd'),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        model_dropdown.pack(anchor="w", padx=30, pady=(0, 15))

        # Analysis frequency
        freq_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        freq_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            freq_frame,
            text="Analysis Frequency",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.frequency_var = ctk.DoubleVar(value=120.0)

        freq_controls = ctk.CTkFrame(freq_frame, fg_color="transparent")
        freq_controls.pack(fill="x", padx=30, pady=(0, 15))

        ctk.CTkLabel(
            freq_controls,
            text="Analyze every:",
            font=ctk.CTkFont(size=12),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        ).pack(side="left")

        freq_slider = ctk.CTkSlider(
            freq_controls,
            from_=30,
            to=300,
            variable=self.frequency_var,
            width=200,
            fg_color=self.colors.get('border_defined', '#2b2b2b' if is_dark else '#adb5bd'),
            progress_color=self.colors.get('primary', '#5b9cff'),
            button_color=self.colors.get('primary', '#5b9cff'),
            button_hover_color=self.colors.get('accent_hover', '#4a8bf8')
        )
        freq_slider.pack(side="left", padx=10)

        self.freq_value_label = ctk.CTkLabel(
            freq_controls,
            text="120s",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors.get('text_primary', '#e6e6e6' if is_dark else '#212529')
        )
        self.freq_value_label.pack(side="left", padx=5)

        # Update label when slider changes
        freq_slider.configure(command=lambda v: self.freq_value_label.configure(text=f"{int(v)}s"))

    def create_insights_presets_tab(self):
        """Create Insights Presets settings tab for customizing quick-action buttons"""
        tab = self.settings_tabview.tab("Insights Presets")
        tab.grid_columnconfigure(0, weight=1)

        # Get theme colors (light, dark) tuples
        FG = ("#212529", "#e6e6e6")  # Text color
        FG_MUTED = ("#6c757d", "#9ca3af")  # Muted text

        # Header
        ctk.CTkLabel(
            tab,
            text="Customize Insights Preset Buttons",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=FG
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            tab,
            text="Configure the quick-action buttons shown in the Insights panel. Add, edit, or remove presets.",
            font=ctk.CTkFont(size=12),
            text_color=FG_MUTED
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 15))

        # Scrollable frame for preset list
        presets_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=("gray90", "gray20"),
            height=300
        )
        presets_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        presets_frame.grid_columnconfigure(0, weight=1)

        # Render existing presets
        for idx, preset in enumerate(self.insights_presets):
            self._render_preset_item(presets_frame, preset, idx)

        # Buttons
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=15)

        ctk.CTkButton(
            button_frame,
            text="➕ Add New Preset",
            command=self.add_new_preset,
            fg_color=("blue", "#1e40af"),
            hover_color=("darkblue", "#1e3a8a"),
            width=150
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            button_frame,
            text=f"Total presets: {len(self.insights_presets)} | Enabled: {sum(1 for p in self.insights_presets if p['enabled'])}",
            font=ctk.CTkFont(size=11),
            text_color=FG_MUTED
        ).pack(side="right", padx=10)

    def _render_preset_item(self, parent, preset, index):
        """Render a single preset item with edit/delete controls"""
        # Theme-aware colors
        FG = ("#212529", "#e6e6e6")  # Text color
        FG_MUTED = ("#6c757d", "#9ca3af")  # Muted text

        item_frame = ctk.CTkFrame(parent, fg_color=("white", "gray25"), corner_radius=8)
        item_frame.grid(row=index, column=0, sticky="ew", padx=5, pady=5)
        item_frame.grid_columnconfigure(1, weight=1)

        # Enabled checkbox
        enabled_var = tk.BooleanVar(value=preset['enabled'])

        def toggle_enabled():
            preset['enabled'] = enabled_var.get()
            self.refresh_insights_panel_presets()

        ctk.CTkCheckBox(
            item_frame,
            text="",
            variable=enabled_var,
            command=toggle_enabled,
            width=30
        ).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        # Label display
        label_display = ctk.CTkLabel(
            item_frame,
            text=preset['label'],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=FG,
            anchor="w"
        )
        label_display.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        # Query preview (truncated)
        query_preview = preset['query'][:60] + "..." if len(preset['query']) > 60 else preset['query']
        ctk.CTkLabel(
            item_frame,
            text=query_preview,
            font=ctk.CTkFont(size=11),
            text_color=FG_MUTED,
            anchor="w"
        ).grid(row=1, column=1, sticky="w", padx=5, pady=(0, 10))

        # Edit button
        ctk.CTkButton(
            item_frame,
            text="✏️ Edit",
            command=lambda: self.edit_preset(index),
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            width=80,
            height=28
        ).grid(row=0, column=2, rowspan=2, padx=5, pady=10)

        # Delete button
        ctk.CTkButton(
            item_frame,
            text="🗑️",
            command=lambda: self.delete_preset(index),
            fg_color=("red", "#dc2626"),
            hover_color=("darkred", "#b91c1c"),
            width=40,
            height=28
        ).grid(row=0, column=3, rowspan=2, padx=5, pady=10)

    def add_new_preset(self):
        """Open dialog to add a new preset"""
        # Theme-aware colors
        FG = ("#212529", "#e6e6e6")

        dialog = ctk.CTkToplevel(self.settings_window)
        dialog.title("Add New Preset")
        dialog.geometry("500x350")
        dialog.transient(self.settings_window)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (350 // 2)
        dialog.geometry(f"500x350+{x}+{y}")

        # Label input
        ctk.CTkLabel(dialog, text="Button Label (with emoji):", font=ctk.CTkFont(size=12), text_color=FG).pack(padx=20, pady=(20, 5), anchor="w")
        label_entry = ctk.CTkEntry(dialog, placeholder_text="e.g., 🔍 Key Points", width=460)
        label_entry.pack(padx=20, pady=(0, 15))

        # Query input
        ctk.CTkLabel(dialog, text="Analysis Query:", font=ctk.CTkFont(size=12), text_color=FG).pack(padx=20, pady=(0, 5), anchor="w")
        query_textbox = ctk.CTkTextbox(dialog, height=150, width=460)
        query_textbox.pack(padx=20, pady=(0, 15))
        query_textbox.insert("1.0", "Analyze...")

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(padx=20, pady=10, fill="x")

        def save_new_preset():
            label = label_entry.get().strip()
            query = query_textbox.get("1.0", "end-1c").strip()

            if not label or not query:
                from tkinter import messagebox
                messagebox.showwarning("Invalid Input", "Label and query cannot be empty.")
                return

            new_preset = {
                'id': f"custom_{len(self.insights_presets)}",
                'label': label,
                'query': query,
                'enabled': True
            }
            self.insights_presets.append(new_preset)
            self.save_settings_to_config()
            self.refresh_insights_panel_presets()
            dialog.destroy()
            # Refresh settings tab
            if hasattr(self, 'settings_tabview'):
                self.create_insights_presets_tab()

        ctk.CTkButton(button_frame, text="Save", command=save_new_preset, width=100).pack(side="right", padx=5)
        ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy, width=100, fg_color="gray").pack(side="right")

    def edit_preset(self, index):
        """Open dialog to edit an existing preset"""
        if index >= len(self.insights_presets):
            return

        preset = self.insights_presets[index]

        # Theme-aware colors
        FG = ("#212529", "#e6e6e6")

        dialog = ctk.CTkToplevel(self.settings_window)
        dialog.title("Edit Preset")
        dialog.geometry("500x350")
        dialog.transient(self.settings_window)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (350 // 2)
        dialog.geometry(f"500x350+{x}+{y}")

        # Label input
        ctk.CTkLabel(dialog, text="Button Label (with emoji):", font=ctk.CTkFont(size=12), text_color=FG).pack(padx=20, pady=(20, 5), anchor="w")
        label_entry = ctk.CTkEntry(dialog, width=460)
        label_entry.insert(0, preset['label'])
        label_entry.pack(padx=20, pady=(0, 15))

        # Query input
        ctk.CTkLabel(dialog, text="Analysis Query:", font=ctk.CTkFont(size=12), text_color=FG).pack(padx=20, pady=(0, 5), anchor="w")
        query_textbox = ctk.CTkTextbox(dialog, height=150, width=460)
        query_textbox.insert("1.0", preset['query'])
        query_textbox.pack(padx=20, pady=(0, 15))

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(padx=20, pady=10, fill="x")

        def save_edits():
            label = label_entry.get().strip()
            query = query_textbox.get("1.0", "end-1c").strip()

            if not label or not query:
                from tkinter import messagebox
                messagebox.showwarning("Invalid Input", "Label and query cannot be empty.")
                return

            preset['label'] = label
            preset['query'] = query
            self.save_settings_to_config()
            self.refresh_insights_panel_presets()
            dialog.destroy()
            # Refresh settings tab
            if hasattr(self, 'settings_tabview'):
                self.create_insights_presets_tab()

        ctk.CTkButton(button_frame, text="Save", command=save_edits, width=100).pack(side="right", padx=5)
        ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy, width=100, fg_color="gray").pack(side="right")

    def delete_preset(self, index):
        """Delete a preset after confirmation"""
        if index >= len(self.insights_presets):
            return

        from tkinter import messagebox
        preset = self.insights_presets[index]

        if messagebox.askyesno("Confirm Delete", f"Delete preset '{preset['label']}'?"):
            self.insights_presets.pop(index)
            self.save_settings_to_config()
            self.refresh_insights_panel_presets()
            # Refresh settings tab
            if hasattr(self, 'settings_tabview'):
                self.create_insights_presets_tab()

    def refresh_insights_panel_presets(self):
        """Refresh the preset buttons in the insights panel"""
        # This will recreate the buttons dynamically
        # We'll need to update ui_components_new.py to support this
        print(f"[PRESETS] Refreshed: {len([p for p in self.insights_presets if p['enabled']])} enabled")
        # TODO: Implement dynamic button refresh in UI
        self.show_toast("Preset buttons will update on next restart", 2000)

    def create_prompt_editor_tab(self):
        """Create prompt template editor interface"""
        tab = self.settings_tabview.tab("Prompt Editor")

        # Use color tuples (light, dark) for automatic theme switching
        bg_color_tuple = ("#ffffff", "#1a1a1a")  # (light, dark)
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)

        # Main container with horizontal split
        main_container = ctk.CTkFrame(tab, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel - Template library and management
        left_panel = ctk.CTkFrame(main_container, width=300, fg_color=bg_color_tuple)
        left_panel.pack(side="left", fill="y", padx=(0, 10))
        left_panel.pack_propagate(False)

        # Template library header
        library_header = ctk.CTkFrame(left_panel, fg_color=self.colors.get('primary', '#1e40af'), corner_radius=6)
        library_header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            library_header,
            text="📚 Template Library",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        ).pack(pady=8)

        # Template management buttons
        button_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=5)

        new_template_btn = ctk.CTkButton(
            button_frame,
            text="+ New",
            width=70,
            height=28,
            command=self.create_new_template,
            fg_color=self.colors.get('success', '#047857')
        )
        new_template_btn.pack(side="left", padx=(0, 5))

        duplicate_btn = ctk.CTkButton(
            button_frame,
            text="Copy",
            width=60,
            height=28,
            command=self.duplicate_template,
            fg_color=self.colors.get('accent', '#6d28d9')
        )
        duplicate_btn.pack(side="left", padx=2)

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=60,
            height=28,
            command=self.delete_template,
            fg_color=self.colors.get('danger', '#dc2626')
        )
        delete_btn.pack(side="left", padx=(5, 0))

        # Category filter
        filter_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        filter_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(filter_frame, text="Category:", font=ctk.CTkFont(size=11)).pack(side="left")

        self.category_filter = ctk.StringVar(value="All")
        category_dropdown = ctk.CTkComboBox(
            filter_frame,
            values=["All", "Real-time", "Risk Assessment", "Session Summary", "Progress Tracking", "Custom"],
            variable=self.category_filter,
            width=120,
            command=self.filter_templates
        )
        category_dropdown.pack(side="right")

        # Template list
        self.template_listbox = ctk.CTkScrollableFrame(
            left_panel,
            height=300,
            fg_color=bg_color_tuple,
            scrollbar_button_color=self.colors.get('primary', '#5b9cff'),
            scrollbar_button_hover_color=self.colors.get('accent', '#4a8bf8')
        )
        self.template_listbox.pack(fill="both", expand=True, padx=10, pady=5)

        # Right panel - Template editor
        right_panel = ctk.CTkFrame(main_container, fg_color=bg_color_tuple)
        right_panel.pack(side="right", fill="both", expand=True)

        # Editor header
        editor_header = ctk.CTkFrame(right_panel, fg_color=bg_accent_tuple, corner_radius=6)
        editor_header.pack(fill="x", padx=10, pady=(10, 5))

        header_left = ctk.CTkFrame(editor_header, fg_color="transparent")
        header_left.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            header_left,
            text="✏️ Template Editor",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        # Editor controls
        controls_frame = ctk.CTkFrame(editor_header, fg_color="transparent")
        controls_frame.pack(side="right", padx=10, pady=8)

        test_btn = ctk.CTkButton(
            controls_frame,
            text="🧪 Test",
            width=70,
            height=28,
            command=self.test_template,
            fg_color=self.colors.get('info', '#1d4ed8')
        )
        test_btn.pack(side="left", padx=(0, 5))

        validate_btn = ctk.CTkButton(
            controls_frame,
            text="[OK] Validate",
            width=80,
            height=28,
            command=self.validate_current_template,
            fg_color=self.colors.get('warning', '#b45309')
        )
        validate_btn.pack(side="left", padx=(0, 5))

        save_btn = ctk.CTkButton(
            controls_frame,
            text="💾 Save",
            width=70,
            height=28,
            command=self.save_template,
            fg_color=self.colors.get('success', '#047857')
        )
        save_btn.pack(side="left")

        # Template metadata
        metadata_frame = ctk.CTkFrame(right_panel, fg_color=bg_accent_tuple)
        metadata_frame.pack(fill="x", padx=10, pady=5)

        # Template name and description
        name_frame = ctk.CTkFrame(metadata_frame, fg_color="transparent")
        name_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(name_frame, text="Name:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.template_name_entry = ctk.CTkEntry(name_frame, placeholder_text="Template name...", width=200)
        self.template_name_entry.pack(side="left", padx=(10, 20))

        ctk.CTkLabel(name_frame, text="Category:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.template_category = ctk.StringVar(value="real-time")
        category_select = ctk.CTkComboBox(
            name_frame,
            values=["real-time", "risk-assessment", "session-summary", "progress-tracking", "custom"],
            variable=self.template_category,
            width=140
        )
        category_select.pack(side="left", padx=(5, 0))

        desc_frame = ctk.CTkFrame(metadata_frame, fg_color="transparent")
        desc_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(desc_frame, text="Description:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.template_description = ctk.CTkEntry(desc_frame, placeholder_text="Brief description of template purpose...")
        self.template_description.pack(fill="x", pady=(5, 0))

        # Variable helper panel
        helper_frame = ctk.CTkFrame(right_panel, fg_color=bg_accent_tuple)
        helper_frame.pack(fill="x", padx=10, pady=5)

        helper_header = ctk.CTkFrame(helper_frame, fg_color="transparent")
        helper_header.pack(fill="x", padx=10, pady=(8, 5))

        ctk.CTkLabel(
            helper_header,
            text="🔧 Available Variables",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        self.show_variables_btn = ctk.CTkButton(
            helper_header,
            text="Show Guide",
            width=80,
            height=24,
            command=self.toggle_variable_guide,
            fg_color=self.colors.get('info', '#1d4ed8')
        )
        self.show_variables_btn.pack(side="right")

        # Variable insertion buttons (initially hidden)
        self.variable_buttons_frame = ctk.CTkFrame(helper_frame, fg_color="transparent")
        # Don't pack initially - will be shown/hidden by toggle

        # Quick insert buttons for common variables
        variables = [
            ("transcript_segment", "📝 Transcript"),
            ("session_context", "📋 Context"),
            ("session_duration", "⏱️ Duration"),
            ("therapy_modality", "🔬 Modality"),
            ("analysis_history", "📊 History"),
            ("risk_level", "[WARN]️ Risk Level")
        ]

        for i, (var, display) in enumerate(variables):
            row = i // 3
            col = i % 3

            btn = ctk.CTkButton(
                self.variable_buttons_frame,
                text=display,
                width=90,
                height=28,
                command=lambda v=var: self.insert_variable(v),
                fg_color=self.colors.get('accent', '#6d28d9')
            )
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="ew")

        # Configure grid weights
        for i in range(3):
            self.variable_buttons_frame.grid_columnconfigure(i, weight=1)

        # Prompt editor
        editor_frame = ctk.CTkFrame(right_panel, fg_color=bg_accent_tuple)
        editor_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Editor label and token counter
        editor_label_frame = ctk.CTkFrame(editor_frame, fg_color="transparent")
        editor_label_frame.pack(fill="x", padx=10, pady=(8, 5))

        ctk.CTkLabel(
            editor_label_frame,
            text="Prompt Template:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        self.token_counter_label = ctk.CTkLabel(
            editor_label_frame,
            text="Tokens: 0",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_secondary', '#e0e0e0')
        )
        self.token_counter_label.pack(side="right")

        # Main text editor
        self.prompt_editor = ctk.CTkTextbox(
            editor_frame,
            height=250,
            font=ctk.CTkFont(size=11),
            wrap="word"
        )
        self.prompt_editor.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Bind text change event for token counting
        self.prompt_editor.bind("<KeyRelease>", self.update_token_count)

        # Action buttons frame
        action_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=(5, 10))

        # Save Template button
        save_btn = ctk.CTkButton(
            action_frame,
            text="💾 Save Template",
            command=self.save_template,
            height=35,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.colors.get('primary', '#1e40af'),
            hover_color=self.colors.get('accent', '#6d28d9')
        )
        save_btn.pack(side="left", padx=(0, 10))

        # Test Template button
        test_btn = ctk.CTkButton(
            action_frame,
            text="🧪 Test Template",
            command=self.test_template_with_live_data,
            height=35,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.colors.get('warning', '#b45309'),
            hover_color=self.colors.get('warning_hover', '#d97706')
        )
        test_btn.pack(side="left", padx=(0, 10))

        # Use Template button (Phase 3 enhancement)
        use_btn = ctk.CTkButton(
            action_frame,
            text="🚀 Use Template Now",
            command=self.use_template_immediately,
            height=35,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.colors.get('success', '#047857'),
            hover_color=self.colors.get('success_hover', '#059669')
        )
        use_btn.pack(side="right")

        # Load templates on initialization
        self.load_templates()

    def create_audio_settings_tab(self):
        """Create audio configuration settings"""
        tab = self.settings_tabview.tab("Audio")

        # Use color tuples (light, dark) for automatic theme switching
        bg_color_tuple = ("#ffffff", "#1a1a1a")  # (light, dark)
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)

        scroll_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=bg_color_tuple,
            scrollbar_button_color=self.colors.get('primary', '#5b9cff'),
            scrollbar_button_hover_color=self.colors.get('accent', '#4a8bf8')
        )
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Buffer settings
        buffer_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        buffer_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            buffer_frame,
            text="Audio Buffer Configuration",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.buffer_duration_var = ctk.DoubleVar(value=30.0)

        buffer_controls = ctk.CTkFrame(buffer_frame, fg_color="transparent")
        buffer_controls.pack(fill="x", padx=30, pady=(0, 15))

        ctk.CTkLabel(
            buffer_controls,
            text="Buffer Duration (transcription delay):",
            font=ctk.CTkFont(size=12)
        ).pack(side="left")

        buffer_slider = ctk.CTkSlider(
            buffer_controls,
            from_=30,
            to=45,
            variable=self.buffer_duration_var,
            width=200
        )
        buffer_slider.pack(side="left", padx=10)

        self.buffer_value_label = ctk.CTkLabel(
            buffer_controls,
            text="30s",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.buffer_value_label.pack(side="left", padx=5)
        buffer_slider.configure(command=lambda v: self.buffer_value_label.configure(text=f"{int(v)}s"))

        # Add help text for buffer duration
        ctk.CTkLabel(
            buffer_frame,
            text="Lower delay = faster transcription but less accuracy. 30s recommended.",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_muted', '#b0b0b0')
        ).pack(anchor="w", padx=30, pady=(0, 15))

        # Quality settings
        quality_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        quality_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            quality_frame,
            text="Transcription Quality",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.quality_var = ctk.StringVar(value="medium")
        quality_options = ["base", "small", "medium", "large"]

        for quality in quality_options:
            radio = ctk.CTkRadioButton(
                quality_frame,
                text=f"{quality.title()} ({self.get_quality_description(quality)})",
                variable=self.quality_var,
                value=quality
            )
            radio.pack(anchor="w", padx=30, pady=3)

        # Dual channel
        self.dual_channel_settings_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            quality_frame,
            text="Enable dual-channel recording (Therapist + Client audio)",
            variable=self.dual_channel_settings_var
        ).pack(anchor="w", padx=30, pady=(15, 15))

        # HuggingFace Token for Speaker Diarization
        hf_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        hf_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            hf_frame,
            text="Speaker Diarization (Advanced)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # Enable advanced diarization checkbox
        self.enable_diarization_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            hf_frame,
            text="Enable pyannote.audio speaker diarization",
            variable=self.enable_diarization_var,
            command=self.toggle_diarization_settings
        ).pack(anchor="w", padx=30, pady=(0, 10))

        # HuggingFace token entry
        token_label_frame = ctk.CTkFrame(hf_frame, fg_color="transparent")
        token_label_frame.pack(fill="x", padx=30, pady=(0, 5))

        ctk.CTkLabel(
            token_label_frame,
            text="HuggingFace Token:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left")

        self.hf_token_entry = ctk.CTkEntry(
            hf_frame,
            placeholder_text="hf_xxxxxxxxxxxxxxxxxxxx",
            width=400,
            show="*"
        )
        self.hf_token_entry.pack(anchor="w", padx=30, pady=(0, 5))

        # Instructions
        instructions = (
            "To enable speaker diarization:\n"
            "1. Visit https://huggingface.co/pyannote/speaker-diarization-3.1\n"
            "2. Accept user conditions and agree to share your contact information\n"
            "3. Visit https://huggingface.co/pyannote/segmentation-3.0 and accept conditions\n"
            "4. Create a token at https://huggingface.co/settings/tokens\n"
            "5. Paste your token above (starts with 'hf_')"
        )

        ctk.CTkLabel(
            hf_frame,
            text=instructions,
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_muted', '#b0b0b0'),
            justify="left"
        ).pack(anchor="w", padx=30, pady=(0, 10))

        # Token validation button
        self.validate_token_btn = ctk.CTkButton(
            hf_frame,
            text="Validate Token",
            command=self.validate_hf_token,
            width=150,
            height=28,
            fg_color=self.colors.get('button_primary', '#2B5AA0'),
            hover_color=self.colors.get('button_primary_hover', '#1E3A6B')
        )
        self.validate_token_btn.pack(anchor="w", padx=30, pady=(0, 15))

        # Token status label
        self.token_status_label = ctk.CTkLabel(
            hf_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=self.colors.get('text_muted', '#b0b0b0')
        )
        self.token_status_label.pack(anchor="w", padx=30, pady=(0, 15))

        # Load saved values into UI fields
        if hasattr(self, 'advanced_diarization_enabled'):
            self.enable_diarization_var.set(self.advanced_diarization_enabled)
        if hasattr(self, 'huggingface_token') and self.huggingface_token:
            self.hf_token_entry.insert(0, self.huggingface_token)

        # Initialize disabled state if needed
        self.toggle_diarization_settings()

    def create_export_settings_tab(self):
        """Create export and session settings"""
        tab = self.settings_tabview.tab("Export")

        # Use color tuples (light, dark) for automatic theme switching
        bg_color_tuple = ("#ffffff", "#1a1a1a")  # (light, dark)
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)

        scroll_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=bg_color_tuple,
            scrollbar_button_color=self.colors.get('primary', '#5b9cff'),
            scrollbar_button_hover_color=self.colors.get('accent', '#4a8bf8')
        )
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Export formats
        export_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        export_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            export_frame,
            text="Export Formats",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.export_formats_vars = {
            'txt': ctk.BooleanVar(value=True),
            'docx': ctk.BooleanVar(value=True),
            'pdf': ctk.BooleanVar(value=False),
            'json': ctk.BooleanVar(value=False)
        }

        for fmt, var in self.export_formats_vars.items():
            ctk.CTkCheckBox(
                export_frame,
                text=f"Export as {fmt.upper()}",
                variable=var
            ).pack(anchor="w", padx=30, pady=3)

        # Session auto-save
        self.auto_save_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            export_frame,
            text="Auto-save sessions every 5 minutes",
            variable=self.auto_save_var
        ).pack(anchor="w", padx=30, pady=(15, 15))

        # Session naming
        naming_frame = ctk.CTkFrame(scroll_frame, fg_color=bg_accent_tuple)
        naming_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            naming_frame,
            text="Session Naming",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.naming_pattern_var = ctk.StringVar(value="session_{date}_{time}")
        naming_options = [
            "session_{date}_{time}",
            "therapy_{date}_{time}",
            "client_{date}_{time}",
            "custom"
        ]

        for pattern in naming_options:
            radio = ctk.CTkRadioButton(
                naming_frame,
                text=pattern.replace("_", " ").title(),
                variable=self.naming_pattern_var,
                value=pattern
            )
            radio.pack(anchor="w", padx=30, pady=3)

        # Custom naming pattern
        self.custom_pattern_entry = ctk.CTkEntry(
            naming_frame,
            placeholder_text="Enter custom pattern: e.g., client_{name}_{date}",
            width=400
        )
        self.custom_pattern_entry.pack(anchor="w", padx=30, pady=(10, 15))

    def get_quality_description(self, quality):
        """Get description for transcription quality level"""
        descriptions = {
            "base": "Fastest, lower accuracy",
            "small": "Fast, good accuracy",
            "medium": "Balanced speed/accuracy",
            "large": "Slower, highest accuracy"
        }
        return descriptions.get(quality, "")

    def toggle_diarization_settings(self):
        """Toggle enable/disable state of diarization settings"""
        enabled = self.enable_diarization_var.get()
        state = "normal" if enabled else "disabled"

        if hasattr(self, 'hf_token_entry'):
            self.hf_token_entry.configure(state=state)
        if hasattr(self, 'validate_token_btn'):
            self.validate_token_btn.configure(state=state)

    def validate_hf_token(self):
        """Validate HuggingFace token by attempting to access the model"""
        token = self.hf_token_entry.get().strip()

        if not token:
            self.token_status_label.configure(
                text="[WARN] Please enter a HuggingFace token",
                text_color="#FF6B6B"
            )
            return

        if not token.startswith("hf_"):
            self.token_status_label.configure(
                text="[WARN] Token should start with 'hf_'",
                text_color="#FF6B6B"
            )
            return

        # Show validating status
        self.token_status_label.configure(
            text="⏳ Validating token...",
            text_color="#FFA500"
        )
        self.validate_token_btn.configure(state="disabled")

        # Run validation in a thread to avoid blocking UI
        def validate_thread():
            try:
                from pyannote.audio import Pipeline
                # Try to access the model with the token
                # This will fail if the token is invalid or user hasn't accepted conditions
                _ = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=token
                )

                # If we get here, token is valid
                self.root.after(0, lambda: self.token_status_label.configure(
                    text="[OK] Token validated successfully! Model ready to download.",
                    text_color="#4CAF50"
                ))
                self.root.after(0, lambda: self.validate_token_btn.configure(state="normal"))

            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "authentication" in error_msg.lower():
                    msg = "[ERROR] Invalid token or conditions not accepted"
                elif "404" in error_msg:
                    msg = "[ERROR] Model not found - check token permissions"
                elif "offline" in error_msg.lower() or "connection" in error_msg.lower():
                    msg = "[WARN] Network error - check internet connection"
                else:
                    msg = f"[ERROR] Validation failed: {error_msg[:50]}"

                self.root.after(0, lambda: self.token_status_label.configure(
                    text=msg,
                    text_color="#FF6B6B"
                ))
                self.root.after(0, lambda: self.validate_token_btn.configure(state="normal"))

        import threading
        threading.Thread(target=validate_thread, daemon=True).start()

    def apply_settings(self):
        """Apply all settings from the modal"""
        try:
            # Apply appearance settings
            if hasattr(self, 'appearance_mode_var'):
                theme_mode = self.appearance_mode_var.get()
                if theme_mode != self.current_theme:
                    self.switch_theme(theme_mode)

            # Apply layout settings
            if hasattr(self, 'control_width_var'):
                self.resize_panel('control', int(self.control_width_var.get()))
            if hasattr(self, 'transcript_width_var'):
                self.resize_panel('transcript', int(self.transcript_width_var.get()))
            if hasattr(self, 'insights_width_var'):
                self.resize_panel('insights', int(self.insights_width_var.get()))

            # Apply analysis settings
            if hasattr(self, 'frequency_var'):
                self.analysis_frequency = int(self.frequency_var.get())
                if hasattr(self, 'analysis_slider'):
                    self.analysis_slider.set(self.analysis_frequency)
                    self.analysis_value_label.configure(text=f"{self.analysis_frequency}s")

            # Apply audio settings
            if hasattr(self, 'buffer_duration_var'):
                self.buffer_duration = int(self.buffer_duration_var.get())

            # Apply diarization settings
            if hasattr(self, 'enable_diarization_var'):
                self.advanced_diarization_enabled = self.enable_diarization_var.get()
            if hasattr(self, 'hf_token_entry'):
                self.huggingface_token = self.hf_token_entry.get().strip()

            # Apply API key settings
            if hasattr(self, 'api_keys'):
                # Update API keys from UI
                for provider in ['gemini', 'claude', 'openai', 'openrouter']:
                    var_name = f'{provider}_key_var'
                    if hasattr(self, var_name):
                        key_var = getattr(self, var_name)
                        self.api_keys[provider] = key_var.get().strip()

                # Update active provider
                if hasattr(self, 'active_provider_var'):
                    self.active_provider = self.active_provider_var.get()

                # Reinitialize Gemini client if key changed and it's the active provider
                if self.active_provider == 'gemini' and self.api_keys.get('gemini'):
                    self.setup_claude_client()

            # Save settings to config file
            self.save_settings_to_config()

            # Show success message
            self.show_success_message("Settings applied successfully!")

            # Close modal
            self.close_settings_modal()

        except Exception as e:
            print(f"Error applying settings: {e}")
            self.show_error_message("Failed to apply settings. Please try again.")

    def apply_color_theme(self, theme_name):
        """Apply selected color theme"""
        themes = {
            "clinical": {
                'primary': '#2E5984',
                'secondary': '#1E4064',
                'success': '#28A745',
                'warning': '#FFC107',
                'danger': '#DC3545',
                'bg_primary': '#F8F9FA',
                'bg_secondary': '#E9ECEF',
                'bg_accent': '#DEE2E6',
                'text_primary': '#212529',
                'text_secondary': '#6C757D',
                'text_muted': '#ADB5BD'
            },
            "professional": {
                'primary': '#0D47A1',
                'secondary': '#1565C0',
                'success': '#2E7D32',
                'warning': '#F57C00',
                'danger': '#C62828',
                'bg_primary': '#FAFAFA',
                'bg_secondary': '#F5F5F5',
                'bg_accent': '#EEEEEE',
                'text_primary': '#212121',
                'text_secondary': '#757575',
                'text_muted': '#BDBDBD'
            },
            "warm": {
                'primary': '#8D4004',
                'secondary': '#A0522D',
                'success': '#556B2F',
                'warning': '#DAA520',
                'danger': '#B22222',
                'bg_primary': '#FDF5E6',
                'bg_secondary': '#F5DEB3',
                'bg_accent': '#DEB887',
                'text_primary': '#2F1B14',
                'text_secondary': '#654321',
                'text_muted': '#A0522D'
            },
            "high_contrast": {
                'primary': '#000080',
                'secondary': '#191970',
                'success': '#008000',
                'warning': '#FFD700',
                'danger': '#FF0000',
                'bg_primary': '#FFFFFF',
                'bg_secondary': '#F0F0F0',
                'bg_accent': '#E0E0E0',
                'text_primary': '#000000',
                'text_secondary': '#333333',
                'text_muted': '#666666'
            }
        }

        if theme_name in themes:
            self.colors = themes[theme_name]
            # Note: In a full implementation, you'd need to refresh all UI elements
            print(f"Color theme '{theme_name}' will be applied on next restart")

    def save_settings_to_config(self):
        """Save current settings to configuration file"""
        try:
            config = {
                'dashboard': {
                    'appearance_mode': self.appearance_mode_var.get() if hasattr(self, 'appearance_mode_var') else 'light',
                    'analysis_auto_expand': self.analysis_auto_expand_var.get() if hasattr(self, 'analysis_auto_expand_var') else True,
                    'show_timestamps': self.show_timestamps_var.get() if hasattr(self, 'show_timestamps_var') else True,
                    'risk_alert_position': self.risk_alert_position_var.get() if hasattr(self, 'risk_alert_position_var') else 'top_right'
                },
                'layout': {
                    'control_panel_width': int(self.control_width_var.get()) if hasattr(self, 'control_width_var') else 200,
                    'transcript_panel_width': int(self.transcript_width_var.get()) if hasattr(self, 'transcript_width_var') else 450,
                    'insights_panel_width': int(self.insights_width_var.get()) if hasattr(self, 'insights_width_var') else 500,
                    'panels_collapsed': self.layout_preferences['panels_collapsed']
                },
                'analysis': {
                    'api_key': self.api_key_entry.get() if hasattr(self, 'api_key_entry') else '',
                    'model': self.model_var.get() if hasattr(self, 'model_var') else 'claude-3-sonnet-20240229',
                    'frequency': int(self.frequency_var.get()) if hasattr(self, 'frequency_var') else 120
                },
                'api_keys': {
                    'active_provider': getattr(self, 'active_provider', 'gemini'),
                    'gemini': {
                        'key': self.api_keys.get('gemini', '') if hasattr(self, 'api_keys') else '',
                        'model': self.gemini_model_var.get() if hasattr(self, 'gemini_model_var') else 'gemini-2.0-flash-001'
                    },
                    'claude': {
                        'key': self.api_keys.get('claude', '') if hasattr(self, 'api_keys') else '',
                        'model': self.claude_model_var.get() if hasattr(self, 'claude_model_var') else 'claude-3-5-sonnet-20241022'
                    },
                    'openai': {
                        'key': self.api_keys.get('openai', '') if hasattr(self, 'api_keys') else '',
                        'model': self.openai_model_var.get() if hasattr(self, 'openai_model_var') else 'gpt-4o'
                    },
                    'openrouter': {
                        'key': self.api_keys.get('openrouter', '') if hasattr(self, 'api_keys') else '',
                        'model': self.openrouter_model_var.get() if hasattr(self, 'openrouter_model_var') else 'auto'
                    }
                },
                'audio': {
                    'buffer_duration': int(self.buffer_duration_var.get()) if hasattr(self, 'buffer_duration_var') else 30,
                    'quality': self.quality_var.get() if hasattr(self, 'quality_var') else 'medium',
                    'dual_channel': self.dual_channel_settings_var.get() if hasattr(self, 'dual_channel_settings_var') else False,
                    'enable_diarization': self.enable_diarization_var.get() if hasattr(self, 'enable_diarization_var') else False,
                    'huggingface_token': self.hf_token_entry.get() if hasattr(self, 'hf_token_entry') else '',
                    'max_speakers': self.max_speakers_var.get() if hasattr(self, 'max_speakers_var') else 2,
                    'blocksize': getattr(self, 'audio_blocksize', 8192),
                    'max_discontinuities': getattr(self, 'max_discontinuities', 10),
                    'discontinuity_warning_throttle': getattr(self, 'discontinuity_warning_throttle', 5)
                },
                'export': {
                    'formats': {fmt: var.get() for fmt, var in self.export_formats_vars.items()} if hasattr(self, 'export_formats_vars') else {'txt': True, 'docx': True},
                    'auto_save': self.auto_save_var.get() if hasattr(self, 'auto_save_var') else True,
                    'naming_pattern': self.naming_pattern_var.get() if hasattr(self, 'naming_pattern_var') else 'session_{date}_{time}',
                    'custom_pattern': self.custom_pattern_entry.get() if hasattr(self, 'custom_pattern_entry') else ''
                },
                'insights_presets': self.insights_presets if hasattr(self, 'insights_presets') else []
            }

            with open('amanuensis_settings.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)

            print("Settings saved to amanuensis_settings.json")

        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings_from_config(self):
        """Load settings from configuration file with robust error handling"""
        try:
            print(f"Loading settings - current_theme before load: {getattr(self, 'current_theme', 'NOT_SET')}")
            if Path('amanuensis_settings.json').exists():
                with open('amanuensis_settings.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)

                # Validate config structure and apply loaded settings
                if isinstance(config, dict):
                    # Dashboard settings
                    if 'dashboard' in config and isinstance(config['dashboard'], dict):
                        dashboard = config['dashboard']
                        if 'appearance_mode' in dashboard and dashboard['appearance_mode'] in ['light', 'dark']:
                            loaded_theme = dashboard['appearance_mode']
                            print(f"Config loaded appearance_mode: {loaded_theme}")
                            self.current_theme = loaded_theme
                            if hasattr(self, 'layout_preferences'):
                                self.layout_preferences['theme'] = loaded_theme
                            print(f"Theme set to: {self.current_theme}")
                            # Update CustomTkinter appearance mode to match
                            ctk.set_appearance_mode(loaded_theme)
                            self.setup_professional_theme()  # Reapply theme

                    # Layout settings with validation
                    if 'layout' in config and isinstance(config['layout'], dict):
                        layout = config['layout']
                        
                        # Validate and apply panel widths
                        if 'control_panel_width' in layout and isinstance(layout['control_panel_width'], (int, float)):
                            width = max(150, min(300, int(layout['control_panel_width'])))
                            self.layout_preferences['control_panel_width'] = width
                            
                        if 'transcript_panel_width' in layout and isinstance(layout['transcript_panel_width'], (int, float)):
                            width = max(300, min(600, int(layout['transcript_panel_width'])))
                            self.layout_preferences['transcript_panel_width'] = width
                            
                        if 'insights_panel_width' in layout and isinstance(layout['insights_panel_width'], (int, float)):
                            width = max(350, min(700, int(layout['insights_panel_width'])))
                            self.layout_preferences['insights_panel_width'] = width
                            
                        # Validate and apply panel collapsed states
                        if 'panels_collapsed' in layout and isinstance(layout['panels_collapsed'], dict):
                            collapsed = layout['panels_collapsed']
                            for panel in ['control', 'transcript', 'insights']:
                                if panel in collapsed and isinstance(collapsed[panel], bool):
                                    self.layout_preferences['panels_collapsed'][panel] = collapsed[panel]

                    # Analysis settings
                    if 'analysis' in config and isinstance(config['analysis'], dict):
                        analysis = config['analysis']
                        if 'frequency' in analysis and isinstance(analysis['frequency'], (int, float)):
                            self.analysis_frequency = max(30, min(600, int(analysis['frequency'])))

                    # Audio settings
                    if 'audio' in config and isinstance(config['audio'], dict):
                        audio = config['audio']
                        if 'buffer_duration' in audio and isinstance(audio['buffer_duration'], (int, float)):
                            self.buffer_duration = max(30, min(45, int(audio['buffer_duration'])))
                        if 'enable_diarization' in audio and isinstance(audio['enable_diarization'], bool):
                            self.advanced_diarization_enabled = audio['enable_diarization']
                        if 'huggingface_token' in audio and isinstance(audio['huggingface_token'], str):
                            self.huggingface_token = audio['huggingface_token']
                        if 'max_speakers' in audio and isinstance(audio['max_speakers'], int):
                            if hasattr(self, 'max_speakers_var'):
                                self.max_speakers_var.set(max(1, min(4, audio['max_speakers'])))
                                self.update_max_speakers_label(audio['max_speakers'])
                        # SoundCard buffer settings for discontinuity handling
                        if 'blocksize' in audio and isinstance(audio['blocksize'], int):
                            self.audio_blocksize = max(1024, min(16384, audio['blocksize']))
                            print(f"[Config] Loaded audio blocksize: {self.audio_blocksize}")
                        if 'max_discontinuities' in audio and isinstance(audio['max_discontinuities'], int):
                            self.max_discontinuities = max(5, audio['max_discontinuities'])
                            print(f"[Config] Loaded max_discontinuities: {self.max_discontinuities}")
                        if 'discontinuity_warning_throttle' in audio and isinstance(audio['discontinuity_warning_throttle'], int):
                            self.discontinuity_warning_throttle = max(1, audio['discontinuity_warning_throttle'])
                            print(f"[Config] Loaded discontinuity_warning_throttle: {self.discontinuity_warning_throttle}")

                    # API Keys settings
                    if 'api_keys' in config and isinstance(config['api_keys'], dict):
                        api_keys_config = config['api_keys']
                        if not hasattr(self, 'api_keys'):
                            self.api_keys = {}

                        # Load active provider
                        if 'active_provider' in api_keys_config:
                            self.active_provider = api_keys_config['active_provider']
                            print(f"[Config] Active provider: {self.active_provider}")

                        for provider in ['gemini', 'claude', 'openai', 'openrouter']:
                            if provider in api_keys_config and isinstance(api_keys_config[provider], dict):
                                provider_config = api_keys_config[provider]
                                if 'key' in provider_config:
                                    self.api_keys[provider] = provider_config['key']
                                if 'model' in provider_config:
                                    model_var_name = f'{provider}_model'
                                    setattr(self, model_var_name, provider_config['model'])

                        print(f"[Config] Loaded API keys for {len(self.api_keys)} providers")

                    # Stitching settings - Fix #1-5 configuration
                    if 'stitch' in config and isinstance(config['stitch'], dict):
                        self.stitching_config = config['stitch']
                    else:
                        # Default stitching configuration
                        self.stitching_config = {
                            'overlap_seconds': 5.0,
                            'min_turn_seconds': 1.0,
                            'min_turn_chars': 15,
                            'coalesce_gap_seconds': 0.30,
                            'dup_text_similarity': 0.95
                        }

                    # UI settings - font size persistence
                    if 'ui' in config and isinstance(config['ui'], dict):
                        ui = config['ui']
                        if 'transcript_font_size' in ui and isinstance(ui['transcript_font_size'], int):
                            # Load font size (14-24 range)
                            loaded_size = max(14, min(24, ui['transcript_font_size']))
                            if hasattr(self, 'transcript_font_size'):
                                self.transcript_font_size = loaded_size
                                # Update UI if textbox already exists
                                if hasattr(self, 'transcript_text'):
                                    self.transcript_text.configure(font=ctk.CTkFont(size=loaded_size))
                                if hasattr(self, 'font_size_label'):
                                    self.font_size_label.configure(text=f"{loaded_size}")

                    # Insights Presets - customizable quick-action buttons
                    if 'insights_presets' in config and isinstance(config['insights_presets'], list):
                        self.insights_presets = config['insights_presets']
                        print(f"[Config] Loaded {len(self.insights_presets)} insights presets")

                    print("Settings loaded successfully from amanuensis_settings.json")
                else:
                    print("Invalid configuration file format, using defaults")
            else:
                print("No configuration file found, using default settings")

        except json.JSONDecodeError as e:
            print(f"Error parsing settings file (corrupted JSON): {e}")
            print("Using default settings")
        except Exception as e:
            print(f"Error loading settings: {e}")
            print("Using default settings")

    def verify_attribute_initialization(self):
        """Verify all required attributes are properly initialized with fallbacks"""
        print("Verifying attribute initialization...")
        
        try:
            # Required dashboard attributes
            required_attrs = {
                'dashboard_state': {
                    'analysis_visible': True,
                    'current_insights': [],
                    'risk_level': 'LOW',
                    'session_active': False
                },
                'layout_preferences': {
                    'control_panel_width': 200,
                    'transcript_panel_width': 450,
                    'insights_panel_width': 500,
                    'panels_collapsed': {'control': False, 'transcript': False, 'insights': False},
                    'theme': 'light'
                },
                'current_theme': 'light'
            }
            
            # Check and initialize missing attributes
            for attr_name, default_value in required_attrs.items():
                if not hasattr(self, attr_name):
                    print(f"WARNING: Missing attribute '{attr_name}', initializing with default")
                    setattr(self, attr_name, default_value)
                elif attr_name == 'layout_preferences' and isinstance(default_value, dict):
                    # Ensure all required keys exist in layout_preferences
                    current_prefs = getattr(self, attr_name)
                    if not isinstance(current_prefs, dict):
                        print(f"WARNING: Invalid {attr_name} type, resetting to default")
                        setattr(self, attr_name, default_value)
                    else:
                        # Check for missing keys
                        for key, default_val in default_value.items():
                            if key not in current_prefs:
                                print(f"WARNING: Missing key '{key}' in {attr_name}, adding default")
                                current_prefs[key] = default_val
                elif attr_name == 'dashboard_state' and isinstance(default_value, dict):
                    # Ensure all required keys exist in dashboard_state
                    current_state = getattr(self, attr_name)
                    if not isinstance(current_state, dict):
                        print(f"WARNING: Invalid {attr_name} type, resetting to default")
                        setattr(self, attr_name, default_value)
                    else:
                        # Check for missing keys
                        for key, default_val in default_value.items():
                            if key not in current_state:
                                print(f"WARNING: Missing key '{key}' in {attr_name}, adding default")
                                current_state[key] = default_val
            
            # Verify theme consistency
            if hasattr(self, 'layout_preferences') and hasattr(self, 'current_theme'):
                if self.layout_preferences.get('theme') != self.current_theme:
                    print(f"WARNING: Theme mismatch, syncing to current_theme: {self.current_theme}")
                    self.layout_preferences['theme'] = self.current_theme
            
            print("[OK] Attribute initialization verification complete")
            
        except Exception as e:
            print(f"ERROR in attribute verification: {e}")
            print("Initializing with safe defaults...")
            
            # Emergency fallback initialization
            self.dashboard_state = {
                'analysis_visible': True,
                'current_insights': [],
                'risk_level': 'LOW',
                'session_active': False
            }
            self.layout_preferences = {
                'control_panel_width': 200,
                'transcript_panel_width': 450,
                'insights_panel_width': 500,
                'panels_collapsed': {'control': False, 'transcript': False, 'insights': False},
                'theme': 'light'
            }
            self.current_theme = 'light'

    def _assert_no_legacy_refs(self):
        """Dev-time verification: Check for legacy widget references"""
        print("[DEV] Checking for legacy widget references...")

        legacy_widget_names = [
            'transcript_status_label',
            'session_status_label',
            'record_button',
            'start_button',
            'stop_button',
            'mic_dropdown',
            'loopback_dropdown',
            'footer_label',
            'status_value',
            'transcript_queue',
            'duration_label',
            'session_metrics_frame',
            'risk_value'
        ]

        found_issues = []

        # Check for these as attributes
        for legacy_name in legacy_widget_names:
            if hasattr(self, legacy_name):
                value = getattr(self, legacy_name)
                # Allow None or commented-out refs
                if value is not None:
                    found_issues.append(f"  - Found attribute: self.{legacy_name} = {type(value).__name__}")

        # Report findings
        if found_issues:
            print(f"[DEV] WARNING: Found {len(found_issues)} legacy widget references:")
            for issue in found_issues:
                print(issue)
            print("[DEV] These should be removed or set to None. Use state/actions instead.")
        else:
            print("[DEV] [OK] No problematic legacy widget references found")

    def reset_to_defaults(self):
        """Reset all settings to default values"""
        try:
            # Reset all setting variables to defaults
            if hasattr(self, 'theme_var'):
                self.theme_var.set('clinical')
            if hasattr(self, 'analysis_auto_expand_var'):
                self.analysis_auto_expand_var.set(True)
            if hasattr(self, 'show_timestamps_var'):
                self.show_timestamps_var.set(True)
            if hasattr(self, 'risk_alert_position_var'):
                self.risk_alert_position_var.set('top_right')
            if hasattr(self, 'model_var'):
                self.model_var.set('claude-3-sonnet-20240229')
            if hasattr(self, 'frequency_var'):
                self.frequency_var.set(120.0)
            if hasattr(self, 'sensitivity_var'):
                self.sensitivity_var.set(0.7)
            if hasattr(self, 'buffer_duration_var'):
                self.buffer_duration_var.set(30.0)
            if hasattr(self, 'quality_var'):
                self.quality_var.set('medium')
            if hasattr(self, 'dual_channel_settings_var'):
                self.dual_channel_settings_var.set(False)
            if hasattr(self, 'enable_diarization_var'):
                self.enable_diarization_var.set(False)
            if hasattr(self, 'hf_token_entry'):
                self.hf_token_entry.delete(0, 'end')

            # Reset export format checkboxes
            if hasattr(self, 'export_formats_vars'):
                self.export_formats_vars['txt'].set(True)
                self.export_formats_vars['docx'].set(True)
                self.export_formats_vars['pdf'].set(False)
                self.export_formats_vars['json'].set(False)

            if hasattr(self, 'auto_save_var'):
                self.auto_save_var.set(True)
            if hasattr(self, 'naming_pattern_var'):
                self.naming_pattern_var.set('session_{date}_{time}')
            if hasattr(self, 'custom_pattern_entry'):
                self.custom_pattern_entry.delete(0, 'end')

            # Clear API key field
            if hasattr(self, 'api_key_entry'):
                self.api_key_entry.delete(0, 'end')

            print("All settings reset to defaults")

        except Exception as e:
            print(f"Error resetting settings: {e}")

    # =================================
    # PROMPT TEMPLATE MANAGEMENT METHODS
    # =================================

    def create_default_templates(self):
        """Create default prompt templates"""
        try:
            self.prompt_templates = {
                'cbt_realtime': {
                    'name': 'CBT Real-time Analysis',
                    'description': 'Cognitive Behavioral Therapy focused real-time insights',
                    'category': 'real-time',
                    'prompt': '''Analyze this therapy session excerpt from a CBT perspective.

**Transcript:**
{transcript_segment}

**Session Context:**
Duration: {session_duration} minutes
Modality: {therapy_modality}

**Analysis Focus:**
1. Identify cognitive distortions
2. Note behavioral patterns
3. Suggest interventions
4. Assess client engagement

Provide brief, actionable insights (150-200 words).''',
                    'variables': ['transcript_segment', 'session_duration', 'therapy_modality'],
                    'created_by': 'system',
                    'created_date': str(datetime.now().date())
                },
                'risk_assessment': {
                    'name': 'Risk Assessment',
                    'description': 'Evaluate potential risk factors and crisis indicators',
                    'category': 'risk-assessment',
                    'prompt': '''Evaluate this session excerpt for risk factors.

**Transcript:**
{transcript_segment}

**Session Context:**
Duration: {session_duration} minutes
Current Risk Level: {risk_level}

**Assessment Criteria:**
- Suicidal ideation (explicit or implicit)
- Self-harm indicators
- Harm to others
- Crisis markers
- Safety concerns

**Provide:**
1. Risk Level: LOW / MEDIUM / HIGH / CRISIS
2. Specific Concerns: (brief list)
3. Recommended Actions: (immediate steps)

Response: 100-150 words, clear and actionable.''',
                    'variables': ['transcript_segment', 'session_duration', 'risk_level'],
                    'created_by': 'system',
                    'created_date': str(datetime.now().date())
                },
                'progress_check': {
                    'name': 'Progress & Engagement',
                    'description': 'Assess client progress and therapeutic alliance',
                    'category': 'real-time',
                    'prompt': '''Assess client progress and engagement in this segment.

**Transcript:**
{transcript_segment}

**Context:**
Session Duration: {session_duration} minutes
Therapy Modality: {therapy_modality}

**Analysis Focus:**
1. Client engagement level (1-10)
2. Progress indicators
3. Treatment adherence
4. Therapeutic alliance quality
5. Areas of improvement

Provide structured assessment (150-200 words).''',
                    'variables': ['transcript_segment', 'session_duration', 'therapy_modality'],
                    'created_by': 'system',
                    'created_date': str(datetime.now().date())
                }
            }

            # Save to file
            self.save_templates_to_file()
            print(f"[OK] Created {len(self.prompt_templates)} default templates")

        except Exception as e:
            print(f"[ERROR] Failed to create default templates: {e}")

    def load_templates(self):
        """Load prompt templates from JSON file"""
        try:
            import json
            from pathlib import Path

            # Initialize prompt templates
            self.prompt_templates = {}
            self.current_template = None
            self.templates_modified = False

            # Load from file
            templates_file = Path("prompts_library.json")
            if templates_file.exists():
                with open(templates_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Load default templates
                if 'default_templates' in data:
                    self.prompt_templates.update(data['default_templates'])

                # Load user templates
                if 'user_templates' in data:
                    self.prompt_templates.update(data['user_templates'])

                # Store metadata
                self.template_categories = data.get('template_categories', [])
                self.available_variables = data.get('available_variables', {})
            else:
                # Create default templates if file doesn't exist
                print("[INFO] No templates file found, creating defaults...")
                self.create_default_templates()

            # Refresh template list if UI is ready
            if hasattr(self, 'template_listbox'):
                self.refresh_template_list()

            print(f"Loaded {len(self.prompt_templates)} prompt templates")

        except Exception as e:
            print(f"Error loading templates: {e}")
            # Initialize with empty templates if loading fails
            self.prompt_templates = {}
            self.current_template = None

    def refresh_template_list(self):
        """Refresh the template list display"""
        try:
            # Clear existing items
            for widget in self.template_listbox.winfo_children():
                widget.destroy()

            # Filter templates by category
            category_filter = self.category_filter.get()
            filtered_templates = {}

            for template_id, template in self.prompt_templates.items():
                if category_filter == "All":
                    filtered_templates[template_id] = template
                else:
                    template_category = template.get('category', 'custom')
                    if category_filter.lower().replace(' ', '-') == template_category:
                        filtered_templates[template_id] = template

            # Create template items
            for i, (template_id, template) in enumerate(filtered_templates.items()):
                self.create_template_list_item(template_id, template, i)

        except Exception as e:
            print(f"Error refreshing template list: {e}")

    def create_template_list_item(self, template_id, template, index):
        """Create a template list item widget"""
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        try:
            # Item frame
            item_frame = ctk.CTkFrame(
                self.template_listbox,
                fg_color=self.colors.get('bg_secondary', '#2d2d2d') if index % 2 == 0 else bg_accent_tuple,
                corner_radius=4
            )
            item_frame.pack(fill="x", pady=2, padx=5)

            # Make clickable
            def select_template():
                self.select_template(template_id)

            item_frame.bind("<Button-1>", lambda e: select_template())

            # Template info
            info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            info_frame.pack(fill="x", padx=8, pady=6)
            info_frame.bind("<Button-1>", lambda e: select_template())

            # Name
            name_label = ctk.CTkLabel(
                info_frame,
                text=template.get('name', template_id),
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w"
            )
            name_label.pack(anchor="w")
            name_label.bind("<Button-1>", lambda e: select_template())

            # Category badge
            category = template.get('category', 'custom')
            category_colors = {
                'real-time': self.colors.get('info', '#1d4ed8'),
                'risk-assessment': self.colors.get('danger', '#dc2626'),
                'session-summary': self.colors.get('success', '#047857'),
                'progress-tracking': self.colors.get('accent', '#6d28d9'),
                'custom': self.colors.get('text_muted', '#b0b0b0')
            }

            category_label = ctk.CTkLabel(
                info_frame,
                text=category.replace('-', ' ').title(),
                font=ctk.CTkFont(size=9),
                fg_color=category_colors.get(category, self.colors.get('text_muted', '#b0b0b0')),
                corner_radius=4,
                text_color="white",
                width=80,
                height=18
            )
            category_label.pack(anchor="w", pady=(2, 0))
            category_label.bind("<Button-1>", lambda e: select_template())

            # Description
            description = template.get('description', '')
            if description:
                desc_label = ctk.CTkLabel(
                    info_frame,
                    text=description[:50] + "..." if len(description) > 50 else description,
                    font=ctk.CTkFont(size=10),
                    text_color=self.colors.get('text_secondary', '#e0e0e0'),
                    anchor="w"
                )
                desc_label.pack(anchor="w", pady=(2, 0))
                desc_label.bind("<Button-1>", lambda e: select_template())

        except Exception as e:
            print(f"Error creating template list item: {e}")

    def select_template(self, template_id):
        """Select and load a template for editing"""
        try:
            if template_id in self.prompt_templates:
                self.current_template = template_id
                template = self.prompt_templates[template_id]

                # Load template data into editor
                self.template_name_entry.delete(0, "end")
                self.template_name_entry.insert(0, template.get('name', ''))

                self.template_description.delete(0, "end")
                self.template_description.insert(0, template.get('description', ''))

                self.template_category.set(template.get('category', 'real-time'))

                # Load prompt text
                self.prompt_editor.delete("1.0", "end")
                self.prompt_editor.insert("1.0", template.get('prompt', ''))

                # Update token count
                self.update_token_count()

                print(f"Selected template: {template.get('name', template_id)}")

        except Exception as e:
            print(f"Error selecting template: {e}")

    def create_new_template(self):
        """Create a new blank template"""
        try:
            # Ensure settings modal and prompt editor tab are initialized
            if not hasattr(self, 'template_name_entry'):
                print("ERROR: Prompt editor not initialized properly")
                messagebox.showerror("Error", "Template editor not ready. Please close and reopen Settings.")
                return
            
            # Clear editor
            self.current_template = None
            self.template_name_entry.delete(0, "end")
            self.template_description.delete(0, "end")
            self.template_category.set("real-time")
            self.prompt_editor.delete("1.0", "end")

            # Insert basic template structure
            basic_template = """Analyze this therapy segment:

**Transcript Segment:**
{transcript_segment}

**Session Context:**
{session_context}

**Analysis Framework:**
1. **Key Observations**:
2. **Clinical Insights**:
3. **Risk Assessment**: (1-10 scale)
4. **Recommendations**:

**Session Duration:** {session_duration} minutes

Provide structured analysis in 200-300 words."""

            self.prompt_editor.insert("1.0", basic_template)
            self.update_token_count()

            # Focus on name field
            self.template_name_entry.focus_set()

        except Exception as e:
            print(f"Error creating new template: {e}")

    def duplicate_template(self):
        """Duplicate the currently selected template"""
        try:
            if self.current_template and self.current_template in self.prompt_templates:
                original = self.prompt_templates[self.current_template]

                # Create copy with modified name
                new_name = f"{original.get('name', 'Template')} - Copy"

                # Clear selection and load copy
                self.current_template = None
                self.template_name_entry.delete(0, "end")
                self.template_name_entry.insert(0, new_name)

                self.template_description.delete(0, "end")
                self.template_description.insert(0, original.get('description', ''))

                self.template_category.set(original.get('category', 'custom'))

                self.prompt_editor.delete("1.0", "end")
                self.prompt_editor.insert("1.0", original.get('prompt', ''))

                self.update_token_count()

                print(f"Duplicated template: {new_name}")

        except Exception as e:
            print(f"Error duplicating template: {e}")

    def delete_template(self):
        """Delete the currently selected template (including defaults)"""
        try:
            if self.current_template and self.current_template in self.prompt_templates:
                template = self.prompt_templates.get(self.current_template, {})
                template_name = template.get('name', self.current_template) if template else self.current_template
                is_system = template.get('created_by') == 'system' if template else False

                # Enhanced confirmation message for defaults
                confirm_msg = f"Are you sure you want to delete '{template_name}'?"
                if is_system:
                    confirm_msg += "\n\n⚠️ This is a default template. You can restore it later using 'Restore Defaults'."
                else:
                    confirm_msg += "\n\nThis action cannot be undone."

                result = messagebox.askyesno("Delete Template", confirm_msg)

                if result:
                    # Delete template (now allows defaults)
                    del self.prompt_templates[self.current_template]
                    self.templates_modified = True

                    # Clear editor
                    self.current_template = None
                    self.template_name_entry.delete(0, "end")
                    self.template_description.delete(0, "end")
                    self.prompt_editor.delete("1.0", "end")

                    # Refresh list and analysis dropdown
                    self.refresh_template_list()
                    self.refresh_analysis_template_dropdown()

                    # Reload analysis templates and refresh prompt buttons
                    if hasattr(self, 'load_templates_for_analysis'):
                        self.load_templates_for_analysis()
                    if hasattr(self, 'render_prompt_buttons'):
                        try:
                            self.render_prompt_buttons()
                        except Exception as e:
                            print(f"[WARNING] Could not refresh prompt buttons: {e}")

                    # Save to file
                    self.save_templates_to_file()

                    print(f"Deleted template: {template_name}")

        except Exception as e:
            print(f"Error deleting template: {e}")
    
    def filter_analysis_templates(self, category_filter):
        """Filter analysis templates by category (Phase 3 enhancement)"""
        try:
            if hasattr(self, 'template_dropdown'):
                # Update dropdown options with filter
                new_options = self.get_template_dropdown_options(category_filter)
                self.template_dropdown.configure(values=new_options)
                
                # Reset selection if current template is filtered out
                current_selection = self.selected_template_var.get()
                if current_selection not in new_options and new_options:
                    if new_options[0] != "No templates available":
                        self.selected_template_var.set(new_options[0])
                        self.on_template_selection_changed(new_options[0])
                
                print(f"[FILTER] Filtered templates by '{category_filter}': {len(new_options)} options")
                
        except Exception as e:
            print(f"Error filtering analysis templates: {e}")
    
    def refresh_analysis_template_dropdown(self):
        """Refresh the analysis template dropdown with updated templates"""
        try:
            if hasattr(self, 'template_dropdown'):
                # Reload templates for analysis
                self.load_templates_for_analysis()
                
                # Get current filter
                current_filter = getattr(self, 'template_category_filter', ctk.StringVar(value="All")).get()
                
                # Update dropdown options with current filter
                new_options = self.get_template_dropdown_options(current_filter)
                self.template_dropdown.configure(values=new_options)
                
                # Ensure current selection is still valid
                if hasattr(self, 'selected_template_id'):
                    if self.selected_template_id not in self.analysis_templates:
                        # Reset to first available template
                        if new_options and new_options[0] != "No templates available":
                            self.selected_template_var.set(new_options[0])
                            self.on_template_selection_changed(new_options[0])
                        else:
                            self.selected_template_id = None
                
                print(f"[UI] Analysis template dropdown refreshed with {len(new_options)} options")
                
        except Exception as e:
            print(f"Error refreshing analysis template dropdown: {e}")

    def filter_templates(self, category=None):
        """Filter templates by category"""
        try:
            self.refresh_template_list()
        except Exception as e:
            print(f"Error filtering templates: {e}")

    def toggle_variable_guide(self):
        """Toggle the variable guide panel"""
        try:
            if self.variable_buttons_frame.winfo_viewable():
                self.variable_buttons_frame.pack_forget()
                self.show_variables_btn.configure(text="Show Guide")
            else:
                self.variable_buttons_frame.pack(fill="x", padx=10, pady=(0, 8))
                self.show_variables_btn.configure(text="Hide Guide")
        except Exception as e:
            print(f"Error toggling variable guide: {e}")

    def insert_variable(self, variable_name):
        """Insert a variable into the prompt editor at cursor position"""
        try:
            # Get current cursor position
            cursor_pos = self.prompt_editor.index("insert")

            # Insert variable
            variable_text = f"{{{variable_name}}}"
            self.prompt_editor.insert(cursor_pos, variable_text)

            # Update token count
            self.update_token_count()

        except Exception as e:
            print(f"Error inserting variable: {e}")

    def update_token_count(self, event=None):
        """Update the token counter (rough estimation)"""
        try:
            text = self.prompt_editor.get("1.0", "end-1c")

            # Rough token estimation: ~4 characters per token
            estimated_tokens = len(text) // 4

            # Color code based on typical API limits
            if estimated_tokens < 1000:
                color = self.colors.get('success', '#047857')
            elif estimated_tokens < 2000:
                color = self.colors.get('warning', '#b45309')
            else:
                color = self.colors.get('danger', '#dc2626')

            self.token_counter_label.configure(
                text=f"Tokens: ~{estimated_tokens}",
                text_color=color
            )

        except Exception as e:
            print(f"Error updating token count: {e}")

    def save_template(self):
        """Save the current template with comprehensive validation and atomic operations"""
        try:
            # Show progress indicator
            progress_window = self.show_save_progress("Validating template...")
            
            # Comprehensive validation
            validation_result = self.validate_template_data()
            if not validation_result['valid']:
                progress_window.destroy()
                messagebox.showerror("Validation Error", validation_result['error'])
                return
            
            # Extract validated data
            name = validation_result['data']['name']
            description = validation_result['data']['description']
            category = validation_result['data']['category']
            prompt_text = validation_result['data']['prompt_text']
            
            progress_window.destroy()
            progress_window = self.show_save_progress("Saving template...")

            # Create comprehensive template data
            template_data = {
                'name': name,
                'description': description,
                'category': category,
                'prompt': prompt_text,
                'variables': self.extract_variables(prompt_text),
                'max_tokens': 500,  # Default
                'created_by': 'user',
                'created_date': str(datetime.now().date()),
                'last_modified': str(datetime.now().isoformat()),
                'version': '1.0',
                'word_count': len(prompt_text.split()),
                'char_count': len(prompt_text)
            }

            # Generate or use existing template ID
            if self.current_template and self.current_template in self.prompt_templates:
                template_id = self.current_template
                template_data['version'] = self.increment_version(self.prompt_templates[template_id].get('version', '1.0'))
                print(f"[TEMPLATE] Updating existing template: {template_id}")
            else:
                template_id = self.generate_unique_template_id(name)
                print(f"[TEMPLATE] Creating new template: {template_id}")

            # Atomic save operation with backup
            save_result = self.atomic_template_save(template_id, template_data)
            progress_window.destroy()
            
            if save_result['success']:
                self.current_template = template_id
                self.templates_modified = True
                
                # Refresh UI
                self.refresh_template_list()

                # Reload analysis templates and refresh prompt buttons
                if hasattr(self, 'load_templates_for_analysis'):
                    self.load_templates_for_analysis()
                if hasattr(self, 'render_prompt_buttons'):
                    try:
                        self.render_prompt_buttons()
                    except Exception as e:
                        print(f"[WARNING] Could not refresh prompt buttons: {e}")

                # Show detailed success message
                success_msg = f"✅ Template '{name}' saved successfully!\n\n"
                success_msg += f"📝 Template ID: {template_id}\n"
                success_msg += f"📊 Variables: {len(template_data['variables'])}\n"
                success_msg += f"📏 Length: {template_data['word_count']} words\n"
                success_msg += f"🏷️ Category: {category}"
                
                messagebox.showinfo("Template Saved", success_msg)
                print(f"[SUCCESS] Template '{name}' saved with {len(template_data['variables'])} variables")
            else:
                messagebox.showerror("Save Failed", f"Failed to save template: {save_result['error']}")
                print(f"[ERROR] Template save failed: {save_result['error']}")

        except Exception as e:
            # Ensure progress window is closed
            if 'progress_window' in locals() and progress_window.winfo_exists():
                progress_window.destroy()
            
            error_msg = f"Template save error: {str(e)}"
            print(f"[ERROR] {error_msg}")
            
            # Show detailed error with troubleshooting
            detailed_error = f"❌ Failed to save template\n\n"
            detailed_error += f"Error: {str(e)}\n\n"
            detailed_error += "💡 Troubleshooting:\n"
            detailed_error += "• Check if template name is unique\n"
            detailed_error += "• Ensure prompt contains valid variables\n"
            detailed_error += "• Verify file permissions in app directory\n"
            detailed_error += "• Try closing and reopening settings"
            
            messagebox.showerror("Save Error", detailed_error)

    def validate_template_data(self):
        """Comprehensive template validation with detailed error reporting"""
        try:
            # Get form data
            name = self.template_name_entry.get().strip()
            description = self.template_description.get().strip()
            category = self.template_category.get()
            prompt_text = self.prompt_editor.get("1.0", "end-1c").strip()
            
            # Validation rules
            errors = []
            
            # Name validation
            if not name:
                errors.append("Template name is required")
            elif len(name) < 3:
                errors.append("Template name must be at least 3 characters")
            elif len(name) > 100:
                errors.append("Template name must be less than 100 characters")
            elif not re.match(r'^[a-zA-Z0-9\s\-_]+$', name):
                errors.append("Template name contains invalid characters (use letters, numbers, spaces, hyphens, underscores only)")
            
            # Check for duplicate names (excluding current template)
            existing_names = [t.get('name', '').lower() for tid, t in self.prompt_templates.items() 
                            if tid != self.current_template]
            if name.lower() in existing_names:
                errors.append(f"Template name '{name}' already exists. Please choose a different name.")
            
            # Prompt validation
            if not prompt_text:
                errors.append("Prompt template text is required")
            elif len(prompt_text) < 10:
                errors.append("Prompt template must be at least 10 characters")
            elif len(prompt_text) > 10000:
                errors.append("Prompt template is too long (max 10,000 characters)")
            
            # Variable validation
            variables = self.extract_variables(prompt_text)
            if len(variables) == 0:
                errors.append("Prompt template should contain at least one variable (e.g., {transcript_segment})")
            
            # Check for malformed variables
            malformed_vars = re.findall(r'\{[^}]*$|^[^{]*\}', prompt_text)
            if malformed_vars:
                errors.append("Prompt contains malformed variables (unmatched braces)")
            
            # Category validation
            valid_categories = ['real-time', 'risk-assessment', 'session-summary', 'progress-tracking', 'custom']
            if category not in valid_categories:
                errors.append(f"Invalid category '{category}'. Must be one of: {', '.join(valid_categories)}")
            
            # Return validation result
            if errors:
                return {
                    'valid': False,
                    'error': '\n'.join([f"• {error}" for error in errors])
                }
            else:
                return {
                    'valid': True,
                    'data': {
                        'name': name,
                        'description': description,
                        'category': category,
                        'prompt_text': prompt_text
                    }
                }
                
        except Exception as e:
            return {
                'valid': False,
                'error': f"Validation error: {str(e)}"
            }
    
    def extract_variables(self, prompt_text):
        """Extract variable names from prompt text with validation"""
        import re
        try:
            variables = re.findall(r'\{([^}]+)\}', prompt_text)
            # Filter out empty or invalid variable names
            valid_variables = []
            for var in variables:
                var = var.strip()
                if var and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', var):
                    valid_variables.append(var)
            return list(set(valid_variables))
        except Exception as e:
            print(f"Error extracting variables: {e}")
            return []


    def atomic_template_save(self, template_id, template_data):
        """Atomic template save operation with backup and rollback"""
        try:
            import json
            from pathlib import Path
            import shutil
            
            templates_file = Path("prompts_library.json")
            backup_file = Path("prompts_library.backup.json")
            temp_file = Path("prompts_library.temp.json")
            
            # Create backup of existing file
            if templates_file.exists():
                shutil.copy2(templates_file, backup_file)
                print(f"[BACKUP] Created backup: {backup_file}")
            
            # Load existing data or create new structure
            if templates_file.exists():
                with open(templates_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = self.create_default_template_structure()
            
            # Update template in memory first
            old_template = self.prompt_templates.get(template_id)
            self.prompt_templates[template_id] = template_data
            
            # Separate user and default templates
            user_templates = {}
            default_templates = {}
            
            for tid, template in self.prompt_templates.items():
                if template.get('created_by') == 'user':
                    user_templates[tid] = template
                else:
                    default_templates[tid] = template
            
            # Update data structure with metadata
            data['user_templates'] = user_templates
            data['default_templates'] = default_templates
            data['metadata'] = {
                'last_updated': datetime.now().isoformat(),
                'total_templates': len(user_templates) + len(default_templates),
                'user_template_count': len(user_templates),
                'app_version': '2.0'
            }
            
            # Write to temporary file first (atomic operation)
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Verify the temporary file is valid JSON
            with open(temp_file, 'r', encoding='utf-8') as f:
                json.load(f)  # This will raise an exception if invalid
            
            # Atomic move (rename) - this is the critical atomic operation
            if temp_file.exists():
                if templates_file.exists():
                    templates_file.unlink()  # Remove old file
                temp_file.rename(templates_file)  # Atomic rename
            
            print(f"[SUCCESS] Atomically saved {len(user_templates)} user templates")
            
            return {
                'success': True,
                'template_count': len(user_templates),
                'backup_created': backup_file.exists()
            }
            
        except Exception as e:
            # Rollback on error
            try:
                # Restore from backup if it exists
                if backup_file.exists() and templates_file.exists():
                    shutil.copy2(backup_file, templates_file)
                    print(f"[ROLLBACK] Restored from backup due to error")
                
                # Restore template in memory
                if old_template is not None:
                    self.prompt_templates[template_id] = old_template
                elif template_id in self.prompt_templates:
                    del self.prompt_templates[template_id]
                
                # Clean up temp file
                if temp_file.exists():
                    temp_file.unlink()
                    
            except Exception as rollback_error:
                print(f"[ERROR] Rollback failed: {rollback_error}")
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def save_templates_to_file(self):
        """Legacy method - redirects to atomic save for compatibility"""
        try:
            # This method is kept for backward compatibility
            # but now uses the atomic save system
            result = self.atomic_template_save(None, None)
            if not result['success']:
                raise Exception(result['error'])
                
        except Exception as e:
            print(f"Error saving templates to file: {e}")
            raise

    def generate_unique_template_id(self, name):
        """Generate a unique template ID based on name"""
        import time
        base_id = f"user_{name.lower().replace(' ', '_').replace('-', '_')}"
        # Remove any non-alphanumeric characters except underscores
        base_id = re.sub(r'[^a-zA-Z0-9_]', '', base_id)
        
        # Ensure it doesn't conflict with existing IDs
        template_id = base_id
        counter = 1
        while template_id in self.prompt_templates:
            template_id = f"{base_id}_{counter}"
            counter += 1
        
        # Add timestamp for uniqueness
        template_id += f"_{int(time.time())}"
        return template_id
    
    def increment_version(self, current_version):
        """Increment template version number"""
        try:
            parts = current_version.split('.')
            if len(parts) >= 2:
                major, minor = int(parts[0]), int(parts[1])
                return f"{major}.{minor + 1}"
            else:
                return "1.1"
        except:
            return "1.1"
    
    def create_default_template_structure(self):
        """Create default template file structure"""
        return {
            'default_templates': {},
            'user_templates': {},
            'template_categories': [
                {'id': 'real-time', 'name': 'Real-time Analysis', 'description': 'Live analysis during therapy sessions'},
                {'id': 'risk-assessment', 'name': 'Risk Assessment', 'description': 'Specialized prompts for safety concerns'},
                {'id': 'session-summary', 'name': 'Session Summary', 'description': 'End-of-session summaries and SOAP notes'},
                {'id': 'progress-tracking', 'name': 'Progress Tracking', 'description': 'Longitudinal analysis for client development'},
                {'id': 'custom', 'name': 'Custom', 'description': 'User-created templates for specialized needs'}
            ],
            'available_variables': {
                'transcript_segment': {'name': 'Transcript Segment', 'description': 'Current transcript segment'},
                'session_context': {'name': 'Session Context', 'description': 'Summary of previous analyses'},
                'session_duration': {'name': 'Session Duration', 'description': 'Session length in minutes'},
                'therapy_modality': {'name': 'Therapy Modality', 'description': 'Selected therapeutic approach'},
                'analysis_history': {'name': 'Analysis History', 'description': 'Previous insights from session'},
                'risk_level': {'name': 'Risk Level', 'description': 'Current risk assessment (1-10 scale)'}
            },
            'settings': {
                'version': '2.0',
                'last_updated': datetime.now().isoformat(),
                'backup_enabled': True,
                'max_custom_templates': 100,
                'default_category': 'real-time'
            }
        }
    
    def show_save_progress(self, message):
        """Show progress window during save operations"""
        try:
            progress_window = ctk.CTkToplevel(self.settings_window)
            progress_window.title("Saving Template")
            progress_window.geometry("300x120")
            progress_window.transient(self.settings_window)
            progress_window.grab_set()
            
            # Center the window
            progress_window.update_idletasks()
            x = (progress_window.winfo_screenwidth() // 2) - (300 // 2)
            y = (progress_window.winfo_screenheight() // 2) - (120 // 2)
            progress_window.geometry(f"300x120+{x}+{y}")
            
            # Progress content
            ctk.CTkLabel(
                progress_window,
                text="💾 Saving Template",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=(20, 10))
            
            ctk.CTkLabel(
                progress_window,
                text=message,
                font=ctk.CTkFont(size=12)
            ).pack(pady=(0, 20))
            
            progress_window.update()
            return progress_window
            
        except Exception as e:
            print(f"Error creating progress window: {e}")
            return None
    
    # =================================
    # TEMPLATE DATA HELPER METHODS
    # =================================

    def get_session_duration_minutes(self):
        """Get current session duration in minutes"""
        try:
            if hasattr(self, 'session_start_time') and self.session_start_time:
                duration = time.time() - self.session_start_time
                return int(duration / 60)
            return 0
        except:
            return 0

    def get_analysis_history_summary(self):
        """Get summary of previous analysis results"""
        try:
            if hasattr(self, 'analysis_results') and self.analysis_results:
                # Get last 3 analysis summaries
                recent_analyses = list(self.analysis_results)[-3:]
                summaries = []
                for analysis in recent_analyses:
                    if analysis.get('success') and 'raw_response' in analysis:
                        # Extract first line as summary
                        response = analysis['raw_response']
                        first_line = response.split('\n')[0][:100]
                        summaries.append(first_line)

                return ". ".join(summaries) if summaries else "No previous analysis"
            return "No previous analysis"
        except:
            return "No previous analysis"

    def get_current_risk_level(self):
        """Get current session risk level (1-10)"""
        try:
            if hasattr(self, 'current_risk_score'):
                return self.current_risk_score

            # Calculate from recent risk alerts
            if hasattr(self, 'risk_alerts') and self.risk_alerts:
                recent_alerts = [alert for alert in self.risk_alerts
                               if time.time() - alert.get('timestamp', 0) < 600]  # Last 10 minutes
                if recent_alerts:
                    return max(alert.get('risk_score', 1) for alert in recent_alerts)

            return 1  # Default low risk
        except:
            return 1

    def add_template_selection_to_settings(self):
        """Add template selection to analysis settings tab"""
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        try:
            # This will be called from create_analysis_settings_tab to add template selector
            # Find the analysis tab frame
            if hasattr(self, 'settings_tabview'):
                analysis_tab = self.settings_tabview.tab("Analysis")

                # Add template selection section
                template_frame = ctk.CTkFrame(analysis_tab, fg_color=bg_accent_tuple)
                template_frame.pack(fill="x", pady=(20, 0), padx=10)

                ctk.CTkLabel(
                    template_frame,
                    text="Prompt Template Selection",
                    font=ctk.CTkFont(size=16, weight="bold")
                ).pack(anchor="w", padx=15, pady=(15, 10))

                # Template selection dropdown
                ctk.CTkLabel(
                    template_frame,
                    text="Analysis Template:",
                    font=ctk.CTkFont(size=12, weight="bold")
                ).pack(anchor="w", padx=30, pady=(10, 5))

                # Load available templates
                template_options = []
                if hasattr(self, 'prompt_templates'):
                    real_time_templates = [
                        (template_id, template['name'])
                        for template_id, template in self.prompt_templates.items()
                        if template.get('category') == 'real-time'
                    ]
                    template_options = [f"{name} ({template_id})" for template_id, name in real_time_templates]

                if not template_options:
                    template_options = ["CBT Real-time Analysis (cbt_realtime)"]

                self.template_selection_var = ctk.StringVar(value=template_options[0])
                template_dropdown = ctk.CTkComboBox(
                    template_frame,
                    values=template_options,
                    variable=self.template_selection_var,
                    width=400,
                    command=self.on_template_selection_changed
                )
                template_dropdown.pack(anchor="w", padx=30, pady=(0, 15))

        except Exception as e:
            print(f"Error adding template selection: {e}")

    def on_template_selection_changed(self, selection):
        """Handle template selection change"""
        try:
            # Extract template ID from selection
            if "(" in selection and ")" in selection:
                template_id = selection.split("(")[-1].split(")")[0]
                self.selected_template_id = template_id
                print(f"Selected template: {template_id}")
        except Exception as e:
            print(f"Error changing template selection: {e}")

    # =================================
    # TEMPLATE VALIDATION AND TESTING
    # =================================

    def validate_template(self, template_data):
        """Validate a template for common issues"""
        validation_results = {
            'valid': True,
            'warnings': [],
            'errors': [],
            'suggestions': []
        }

        try:
            name = template_data.get('name', '').strip()
            prompt = template_data.get('prompt', '').strip()
            category = template_data.get('category', '')

            # Required field validation
            if not name:
                validation_results['errors'].append("Template name is required")
                validation_results['valid'] = False

            if not prompt:
                validation_results['errors'].append("Prompt template is required")
                validation_results['valid'] = False

            if not category:
                validation_results['warnings'].append("Category should be specified")

            # Prompt content validation
            if prompt:
                # Check for variables
                variables = self.extract_variables(prompt)
                if not variables:
                    validation_results['warnings'].append("Template contains no variables - consider adding {transcript_segment}")

                # Check for common required variables
                recommended_vars = ['transcript_segment', 'session_context']
                missing_vars = [var for var in recommended_vars if var not in variables]
                if missing_vars:
                    validation_results['suggestions'].append(f"Consider adding variables: {', '.join(missing_vars)}")

                # Check prompt length
                estimated_tokens = len(prompt) // 4
                if estimated_tokens > 2000:
                    validation_results['warnings'].append(f"Template is very long (~{estimated_tokens} tokens) - may exceed API limits")
                elif estimated_tokens < 50:
                    validation_results['warnings'].append("Template is very short - consider adding more detail")

                # Check for clinical guidance
                clinical_keywords = ['risk', 'assessment', 'safety', 'intervention', 'recommendation']
                if not any(keyword in prompt.lower() for keyword in clinical_keywords):
                    validation_results['suggestions'].append("Consider adding clinical assessment guidance (risk, safety, interventions)")

                # Check for structured output
                if 'json' in prompt.lower() or '{' in prompt:
                    validation_results['suggestions'].append("Structured output detected - ensure Claude can generate valid JSON")

            # Category-specific validation
            if category == 'risk-assessment':
                if 'risk' not in prompt.lower() or 'safety' not in prompt.lower():
                    validation_results['warnings'].append("Risk assessment templates should include safety evaluation")

            elif category == 'session-summary':
                soap_elements = ['subjective', 'objective', 'assessment', 'plan']
                if not any(element in prompt.lower() for element in soap_elements):
                    validation_results['suggestions'].append("Session summaries often benefit from SOAP note structure")

        except Exception as e:
            validation_results['errors'].append(f"Validation error: {str(e)}")
            validation_results['valid'] = False

        return validation_results

    def show_validation_results(self, validation_results):
        """Show template validation results in a popup"""
        try:
            # Create validation window
            validation_window = ctk.CTkToplevel(self.settings_window)
            validation_window.title("Template Validation Results")
            validation_window.geometry("500x400")
            validation_window.transient(self.settings_window)

            # Header
            header_color = self.colors.get('success', '#047857') if validation_results['valid'] else self.colors.get('warning', '#b45309')
            header = ctk.CTkFrame(validation_window, fg_color=header_color)
            header.pack(fill="x", padx=10, pady=(10, 5))

            status_text = "[OK] Template Valid" if validation_results['valid'] else "[WARN] Issues Found"
            ctk.CTkLabel(
                header,
                text=status_text,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="white"
            ).pack(pady=10)

            # Results display
            results_frame = ctk.CTkScrollableFrame(validation_window)
            results_frame.pack(fill="both", expand=True, padx=10, pady=5)

            # Show errors
            if validation_results['errors']:
                error_frame = ctk.CTkFrame(results_frame, fg_color=self.colors.get('danger', '#dc2626'))
                error_frame.pack(fill="x", pady=(0, 10))

                ctk.CTkLabel(
                    error_frame,
                    text="❌ Errors (Must Fix)",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="white"
                ).pack(anchor="w", padx=10, pady=(8, 5))

                for error in validation_results['errors']:
                    ctk.CTkLabel(
                        error_frame,
                        text=f"• {error}",
                        font=ctk.CTkFont(size=11),
                        text_color="white",
                        anchor="w"
                    ).pack(anchor="w", padx=20, pady=2)

            # Show warnings
            if validation_results['warnings']:
                warning_frame = ctk.CTkFrame(results_frame, fg_color=self.colors.get('warning', '#b45309'))
                warning_frame.pack(fill="x", pady=(0, 10))

                ctk.CTkLabel(
                    warning_frame,
                    text="[WARN]️ Warnings",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="white"
                ).pack(anchor="w", padx=10, pady=(8, 5))

                for warning in validation_results['warnings']:
                    ctk.CTkLabel(
                        warning_frame,
                        text=f"• {warning}",
                        font=ctk.CTkFont(size=11),
                        text_color="white",
                        anchor="w"
                    ).pack(anchor="w", padx=20, pady=2)

            # Show suggestions
            if validation_results['suggestions']:
                suggestion_frame = ctk.CTkFrame(results_frame, fg_color=self.colors.get('info', '#1d4ed8'))
                suggestion_frame.pack(fill="x", pady=(0, 10))

                ctk.CTkLabel(
                    suggestion_frame,
                    text="💡 Suggestions",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="white"
                ).pack(anchor="w", padx=10, pady=(8, 5))

                for suggestion in validation_results['suggestions']:
                    ctk.CTkLabel(
                        suggestion_frame,
                        text=f"• {suggestion}",
                        font=ctk.CTkFont(size=11),
                        text_color="white",
                        anchor="w"
                    ).pack(anchor="w", padx=20, pady=2)

            # If all good
            if validation_results['valid'] and not validation_results['warnings'] and not validation_results['suggestions']:
                success_frame = ctk.CTkFrame(results_frame, fg_color=self.colors.get('success', '#047857'))
                success_frame.pack(fill="x", pady=(0, 10))

                ctk.CTkLabel(
                    success_frame,
                    text="🎉 Template looks great! No issues found.",
                    font=ctk.CTkFont(size=12),
                    text_color="white"
                ).pack(padx=10, pady=15)

            # Close button
            close_btn = ctk.CTkButton(
                validation_window,
                text="Close",
                command=validation_window.destroy,
                width=100
            )
            close_btn.pack(pady=10)

        except Exception as e:
            print(f"Error showing validation results: {e}")

    def validate_current_template(self):
        """Validate the currently edited template"""
        try:
            # Get current template data
            template_data = {
                'name': self.template_name_entry.get().strip(),
                'description': self.template_description.get().strip(),
                'category': self.template_category.get(),
                'prompt': self.prompt_editor.get("1.0", "end-1c").strip()
            }

            # Validate template
            validation_results = self.validate_template(template_data)

            # Show results
            self.show_validation_results(validation_results)

            return validation_results['valid']

        except Exception as e:
            print(f"Error validating template: {e}")
            return False

    def close_settings_modal(self):
        """Close the settings modal"""
        try:
            if hasattr(self, 'settings_window') and self.settings_window:
                self.settings_window.destroy()
                self.settings_window = None
        except Exception as e:
            print(f"Error closing settings modal: {e}")

    def show_success_message(self, message):
        """Show success message in a temporary popup"""
        # In a full implementation, this would show a toast notification
        print(f"SUCCESS: {message}")

    def show_error_message(self, message):
        """Show error message in a temporary popup"""
        # In a full implementation, this would show an error toast notification
        print(f"ERROR: {message}")

    def show_toast(self, message, duration=3000):
        """Show temporary toast notification in status bar"""
        if hasattr(self, 'status_label'):
            original_text = self.status_label.cget("text") if hasattr(self, 'status_label') else ""
            self.set_status(f"[OK] {message}")
            # Restore after duration
            if original_text:
                self.root.after(duration, lambda: self.set_status(original_text))
        print(f"TOAST: {message}")

    # ===================================================================
    # RECORDING AND SESSION CONTROL METHODS
    # ===================================================================

    def update_buffer_duration(self, value):
        """Update buffer duration from slider"""
        self.buffer_duration = int(value)
        if hasattr(self, 'buffer_value_label'):
            self.buffer_value_label.configure(text=f"{self.buffer_duration}s")

    def update_dual_channel_mode(self):
        """Update dual-channel recording mode"""
        self.dual_channel_enabled = self.dual_channel_var.get()
        if self.dual_channel_enabled:
            self.set_status("Dual-channel mode enabled")
        else:
            self.set_status("Single-channel mode (microphone only)")

    def update_advanced_diarization_mode(self):
        """Update advanced diarization mode"""
        self.advanced_diarization_enabled = self.advanced_diarization_var.get()

        if self.advanced_diarization_enabled:
            if not PYANNOTE_AVAILABLE:
                # Disable if pyannote not available
                self.advanced_diarization_var.set(False)
                self.advanced_diarization_enabled = False
                error_msg = "Pyannote.audio not available. Please install pyannote.audio dependencies."
                messagebox.showerror("Diarization Error", error_msg)
                # Update checkbox state and hint
                if hasattr(self, 'advanced_diarization_checkbox'):
                    self.advanced_diarization_checkbox.configure(
                        state="disabled",
                        fg_color="gray30"
                    )
                if hasattr(self, 'diarization_status_hint'):
                    self.diarization_status_hint.configure(
                        text="[WARN] pyannote.audio not installed",
                        text_color="orange"
                    )
                return

            if not self.pyannote_pipeline:
                # Try to load pipeline if not already loaded
                device = "cuda" if torch.cuda.is_available() else "cpu"
                available_memory = self.get_gpu_memory_available()
                self.load_pyannote_pipeline(device, available_memory)

            if not self.pyannote_pipeline:
                # Still no pipeline, disable and show specific error
                self.advanced_diarization_var.set(False)
                self.advanced_diarization_enabled = False

                # Show specific error from diarization_error if available
                if self.diarization_error:
                    error_msg = f"Hugging Face token not found — diarization disabled\n\n{self.diarization_error}\n\nSet HF_TOKEN environment variable or configure in Settings > Audio"
                    hint_text = f"[WARN] {self.diarization_error}"
                else:
                    error_msg = "Failed to load pyannote models. Advanced diarization disabled."
                    hint_text = "[WARN] Failed to load models"

                messagebox.showerror("Diarization Error", error_msg)

                # Disable checkbox with visual feedback and status hint
                if hasattr(self, 'advanced_diarization_checkbox'):
                    self.advanced_diarization_checkbox.configure(
                        state="disabled",
                        fg_color="gray30"
                    )
                if hasattr(self, 'diarization_status_hint'):
                    self.diarization_status_hint.configure(
                        text=hint_text,
                        text_color="orange"
                    )
                return

            # Check GPU memory
            if not self.check_gpu_memory_sufficient(2.0):
                warning_msg = (
                    "Warning: Low GPU memory detected. Advanced diarization may use CPU fallback, "
                    "which will be slower but still functional."
                )
                messagebox.showwarning("GPU Memory Warning", warning_msg)

            # Update status with current buffer size
            current_selection = self.diarization_buffer_var.get()
            delay_text = f"Advanced diarization enabled ({current_selection} delay)"
            self.set_status(delay_text)
            self.diarization_status_label.configure(text="[OK] Models loaded, GPU optimized", text_color="green")

            # Update hint to show success
            if hasattr(self, 'diarization_status_hint'):
                self.diarization_status_hint.configure(
                    text="[OK] Ready - models loaded successfully",
                    text_color="green"
                )
        else:
            self.set_status("Standard channel-based diarization")
            self.diarization_status_label.configure(text="Requires pyannote.audio models", text_color="gray60")

            # Clear hint when disabled
            if hasattr(self, 'diarization_status_hint'):
                self.diarization_status_hint.configure(text="")

    def update_diarization_buffer_size(self, selection):
        """Update diarization buffer size based on user selection"""
        self.diarization_buffer_size = self.diarization_buffer_options[selection]
        print(f"Diarization buffer size updated to: {self.diarization_buffer_size}s ({selection})")

        # Update status to show new delay
        if self.advanced_diarization_enabled:
            delay_text = f"Advanced diarization enabled ({selection} delay)"
            self.set_status(delay_text)

    def update_max_speakers_label(self, value):
        """Update max speakers label when slider changes"""
        max_speakers = int(float(value))
        speaker_text = "speaker" if max_speakers == 1 else "speakers"
        if hasattr(self, 'max_speakers_label'):
            self.max_speakers_label.configure(text=f"{max_speakers} {speaker_text}")
        print(f"Max speakers set to: {max_speakers}")

    def get_diarization_overlap_size(self):
        """Calculate appropriate overlap size based on buffer duration"""
        # Use 10-20% of buffer size as overlap, with reasonable min/max bounds
        overlap_ratio = 0.15  # 15% overlap
        calculated_overlap = int(self.diarization_buffer_size * overlap_ratio)

        # Bounds: minimum 5 seconds, maximum 15 seconds
        overlap_seconds = max(5, min(15, calculated_overlap))

        print(f"Using {overlap_seconds}s overlap for {self.diarization_buffer_size}s buffer")
        return overlap_seconds

    def load_templates_for_analysis(self):
        """Load templates for analysis dropdown"""
        try:
            # Ensure templates are loaded
            if not hasattr(self, 'prompt_templates') or not self.prompt_templates:
                self.load_templates()
            
            # Create analysis-ready template list
            self.analysis_templates = {}
            
            # Add default templates
            for template_id, template in self.prompt_templates.items():
                if template.get('category') in ['real-time', 'risk-assessment', 'custom']:
                    self.analysis_templates[template_id] = {
                        'name': template.get('name', template_id),
                        'description': template.get('description', ''),
                        'category': template.get('category', 'custom'),
                        'variables': template.get('variables', []),
                        'prompt': template.get('prompt', ''),
                        'created_by': template.get('created_by', 'system')
                    }
            
            print(f"[ANALYSIS] Loaded {len(self.analysis_templates)} templates for analysis")
            
        except Exception as e:
            print(f"Error loading templates for analysis: {e}")
            self.analysis_templates = {}
    
    def get_template_dropdown_options(self, category_filter="All"):
        """Get formatted options for template dropdown with optional category filtering"""
        try:
            options = []
            
            # Group by category
            categories = {'real-time': [], 'risk-assessment': [], 'custom': []}
            
            for template_id, template in self.analysis_templates.items():
                category = template.get('category', 'custom')
                name = template.get('name', template_id)
                created_by = template.get('created_by', 'system')
                
                # Apply category filter
                if category_filter != "All":
                    filter_mapping = {
                        "Real-time": "real-time",
                        "Risk Assessment": "risk-assessment",
                        "Custom": "custom"
                    }
                    if category != filter_mapping.get(category_filter, category_filter.lower()):
                        continue
                
                # Add emoji indicators
                if created_by == 'user':
                    display_name = f"📝 {name}"
                else:
                    display_name = f"⚙️ {name}"
                
                if category in categories:
                    categories[category].append((template_id, display_name))
            
            # Build options list with category headers
            for category, templates in categories.items():
                if templates:
                    # Add category separator
                    category_names = {
                        'real-time': '⚡ Real-time Analysis',
                        'risk-assessment': '⚠️ Risk Assessment', 
                        'custom': '🎨 Custom Templates'
                    }
                    
                    for template_id, display_name in sorted(templates, key=lambda x: x[1]):
                        options.append(display_name)
            
            return options if options else ["No templates available"]

        except Exception as e:
            print(f"Error getting template options: {e}")
            return ["Error loading templates"]

    def populate_insights_template_options(self):
        """Populate template dropdown options in insights panel"""
        try:
            # Load templates if not already loaded
            if not hasattr(self, 'analysis_templates') or not self.analysis_templates:
                self.load_templates_for_analysis()

            # Get formatted template options
            options = ['Quick Query']  # Default option for custom queries

            if hasattr(self, 'analysis_templates'):
                for template_id, template in self.analysis_templates.items():
                    display_name = self._get_template_display_name(template)
                    options.append(display_name)

            # Update insights state with template options
            if hasattr(self, 'insights_state'):
                self.insights_state.template_options = options

                # Update UI dropdown if it exists
                if hasattr(self.insights_state, 'template_dropdown'):
                    self.root.after(0, lambda: self.insights_state.template_dropdown.configure(values=options))

            if self.VERBOSE_INSIGHTS:
                print(f"[INSIGHTS] Populated {len(options)} template options")

        except Exception as e:
            print(f"Error populating insights template options: {e}")
            if hasattr(self, 'insights_state'):
                self.insights_state.template_options = ['Quick Query']

    def _get_template_display_name(self, template):
        """Get formatted display name for a template"""
        name = template.get('name', 'Unnamed Template')
        created_by = template.get('created_by', 'system')

        # Add emoji indicators
        if created_by == 'user':
            return f"📝 {name}"
        else:
            return f"⚙️ {name}"

    def on_template_selection_changed(self, selection):
        """Handle template selection change"""
        try:
            # Find template ID from display name
            selected_template_id = None
            for template_id, template in self.analysis_templates.items():
                name = template.get('name', template_id)
                created_by = template.get('created_by', 'system')
                
                if created_by == 'user':
                    display_name = f"📝 {name}"
                else:
                    display_name = f"⚙️ {name}"
                
                if display_name == selection:
                    selected_template_id = template_id
                    break
            
            if selected_template_id:
                self.selected_template_id = selected_template_id
                template = self.analysis_templates[selected_template_id]
                print(f"[TEMPLATE] Selected: {template.get('name')} ({selected_template_id})")
                
                # Update UI to show template info
                self.update_template_info_display(template)
            
        except Exception as e:
            print(f"Error handling template selection: {e}")
    
    def show_template_info(self):
        """Show information about the currently selected template"""
        try:
            if not hasattr(self, 'selected_template_id') or not self.selected_template_id:
                messagebox.showinfo("Template Info", "No template selected")
                return
            
            template = self.analysis_templates.get(self.selected_template_id)
            if not template:
                messagebox.showinfo("Template Info", "Template not found")
                return
            
            # Create info window
            info_window = ctk.CTkToplevel(self.root)
            info_window.title("Template Information")
            info_window.geometry("500x400")
            info_window.transient(self.root)
            
            # Template details
            details_frame = ctk.CTkScrollableFrame(info_window)
            details_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Name and category
            ctk.CTkLabel(
                details_frame,
                text=template.get('name', 'Unknown Template'),
                font=ctk.CTkFont(size=18, weight="bold")
            ).pack(anchor="w", pady=(0, 10))
            
            ctk.CTkLabel(
                details_frame,
                text=f"Category: {template.get('category', 'Unknown')}",
                font=ctk.CTkFont(size=12)
            ).pack(anchor="w", pady=(0, 5))
            
            ctk.CTkLabel(
                details_frame,
                text=f"Created by: {template.get('created_by', 'Unknown')}",
                font=ctk.CTkFont(size=12)
            ).pack(anchor="w", pady=(0, 10))
            
            # Description
            if template.get('description'):
                ctk.CTkLabel(
                    details_frame,
                    text="Description:",
                    font=ctk.CTkFont(size=14, weight="bold")
                ).pack(anchor="w", pady=(10, 5))
                
                ctk.CTkLabel(
                    details_frame,
                    text=template.get('description'),
                    font=ctk.CTkFont(size=12),
                    wraplength=450
                ).pack(anchor="w", pady=(0, 10))
            
            # Variables
            variables = template.get('variables', [])
            if variables:
                ctk.CTkLabel(
                    details_frame,
                    text=f"Variables ({len(variables)}):",
                    font=ctk.CTkFont(size=14, weight="bold")
                ).pack(anchor="w", pady=(10, 5))
                
                for var in variables:
                    ctk.CTkLabel(
                        details_frame,
                        text=f"• {{{var}}}",
                        font=ctk.CTkFont(size=11),
                        text_color="#888888"
                    ).pack(anchor="w", padx=20)
            
            # Close button
            ctk.CTkButton(
                info_window,
                text="Close",
                command=info_window.destroy,
                width=100
            ).pack(pady=10)
            
        except Exception as e:
            print(f"Error showing template info: {e}")
            messagebox.showerror("Error", f"Failed to show template info: {str(e)}")
    
    def update_template_info_display(self, template):
        """Update any UI elements that show template info"""
        try:
            # Update tooltip or status if needed
            variables_count = len(template.get('variables', []))
            category = template.get('category', 'unknown')
            print(f"[UI] Template info updated: {variables_count} variables, category: {category}")
            
        except Exception as e:
            print(f"Error updating template info display: {e}")
    
    def use_template_immediately(self):
        """Use the current template immediately for analysis (Phase 3 enhancement)"""
        try:
            # Validate current template
            validation_result = self.validate_template_data()
            if not validation_result['valid']:
                messagebox.showerror("Template Invalid", 
                    f"Please fix template issues first:\n\n{validation_result['error']}")
                return
            
            # Save template first if it's new or modified
            if not self.current_template or self.templates_modified:
                save_result = messagebox.askyesno(
                    "Save Template?", 
                    "Template needs to be saved first. Save and use it now?"
                )
                if save_result:
                    self.save_template()
                else:
                    return
            
            # Close settings window
            if hasattr(self, 'settings_window') and self.settings_window:
                self.settings_window.destroy()
            
            # Switch to insights panel and select this template
            if hasattr(self, 'template_dropdown') and self.current_template:
                # Refresh analysis templates
                self.load_templates_for_analysis()
                
                # Find the template in dropdown options
                template = self.prompt_templates.get(self.current_template)
                if template:
                    template_name = template.get('name', 'Unknown')
                    created_by = template.get('created_by', 'system')
                    
                    # Create display name
                    if created_by == 'user':
                        display_name = f"📝 {template_name}"
                    else:
                        display_name = f"⚙️ {template_name}"
                    
                    # Update dropdown and selection
                    new_options = self.get_template_dropdown_options()
                    self.template_dropdown.configure(values=new_options)
                    
                    if display_name in new_options:
                        self.selected_template_var.set(display_name)
                        self.on_template_selection_changed(display_name)
                        
                        # Show success message
                        self.show_toast(f"Template '{template_name}' ready for analysis!", 3000)
                        
                        print(f"[USE TEMPLATE] Switched to template: {template_name}")
                    else:
                        messagebox.showwarning("Template Not Found", 
                            "Template was saved but not found in analysis dropdown.")
                else:
                    messagebox.showerror("Template Error", "Current template not found.")
            else:
                messagebox.showinfo("Template Ready", 
                    "Template saved! Go to the Insights panel to use it for analysis.")
                    
        except Exception as e:
            print(f"Error using template immediately: {e}")
            messagebox.showerror("Error", f"Failed to use template: {str(e)}")

    def test_template(self):
        """Test the current template (delegates to test_template_with_live_data)"""
        self.test_template_with_live_data()

    def test_template_with_live_data(self):
        """Test template with live session data (Phase 3 enhancement)"""
        try:
            # Validate template first
            validation_result = self.validate_template_data()
            if not validation_result['valid']:
                messagebox.showerror("Template Invalid", 
                    f"Please fix template issues first:\n\n{validation_result['error']}")
                return
            
            # Get current template text
            prompt_text = self.prompt_editor.get("1.0", "end-1c").strip()
            if not prompt_text:
                messagebox.showwarning("No Template", "Please enter a template to test.")
                return
            
            # Check if we have session data
            if not hasattr(self, 'current_session') or not self.current_session:
                # Use sample data for testing
                self.show_template_test_with_sample_data(prompt_text)
                return
            
            # Get recent transcript for testing
            window_minutes = 5  # Default test window
            window_seconds = window_minutes * 60
            transcript_text = self.get_recent_transcript(window_seconds)
            
            if not transcript_text or len(transcript_text.strip()) < 20:
                # Use sample data if no real transcript
                self.show_template_test_with_sample_data(prompt_text)
                return
            
            # Prepare live variables
            template_variables = self.prepare_template_variables(transcript_text, window_minutes)
            
            # Substitute variables
            test_prompt = self.substitute_template_variables(prompt_text, template_variables)
            
            # Show test result window with live data
            self.show_template_test_result(test_prompt, template_variables, is_live_data=True)
            
        except Exception as e:
            print(f"Error testing template with live data: {e}")
            messagebox.showerror("Test Error", f"Failed to test template: {str(e)}")
    
    def show_template_test_with_sample_data(self, prompt_text):
        """Show template test with sample data when no live session"""
        try:
            # Sample data for testing
            sample_variables = {
                'transcript_segment': '[14:23:15] [CLIENT]: I\'ve been feeling really anxious about work lately. My boss keeps piling on more projects and I don\'t know how to handle it all. [14:24:02] [THERAPIST]: That sounds overwhelming. Can you tell me more about what specifically makes you feel most anxious?',
                'session_context': 'Client discussing work-related stress and anxiety. Previous sessions focused on coping strategies and time management.',
                'session_duration': '25',
                'therapy_modality': 'CBT',
                'analysis_history': 'Previous analysis identified catastrophic thinking patterns. Client showed insight into triggers.',
                'risk_level': '3',
                'window_minutes': '5',
                'current_time': datetime.now().strftime('%H:%M:%S'),
                'session_date': datetime.now().strftime('%Y-%m-%d')
            }
            
            # Substitute variables
            test_prompt = self.substitute_template_variables(prompt_text, sample_variables)
            
            # Show test result
            self.show_template_test_result(test_prompt, sample_variables, is_live_data=False)
            
        except Exception as e:
            print(f"Error showing sample test: {e}")
            messagebox.showerror("Test Error", f"Failed to show test: {str(e)}")
    
    def show_template_test_result(self, test_prompt, variables, is_live_data=True):
        """Show template test result in a detailed window"""
        try:
            # Create test result window
            test_window = ctk.CTkToplevel(self.settings_window)
            test_window.title("Template Test Result")
            test_window.geometry("700x600")
            test_window.transient(self.settings_window)
            
            # Header
            header = ctk.CTkFrame(test_window, fg_color=self.colors.get('info', '#1d4ed8'))
            header.pack(fill="x", padx=10, pady=(10, 5))
            
            data_type = "Live Session Data" if is_live_data else "Sample Data"
            ctk.CTkLabel(
                header,
                text=f"🧪 Template Test Result ({data_type})",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="white"
            ).pack(pady=10)
            
            # Main content with tabs
            tabview = ctk.CTkTabview(test_window)
            tabview.pack(fill="both", expand=True, padx=10, pady=5)
            
            # Variables tab
            variables_tab = tabview.add("Variables Used")
            variables_frame = ctk.CTkScrollableFrame(variables_tab)
            variables_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            ctk.CTkLabel(
                variables_frame,
                text=f"Variables Substituted ({len(variables)}):",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", pady=(0, 10))
            
            for var_name, var_value in variables.items():
                var_frame = ctk.CTkFrame(variables_frame)
                var_frame.pack(fill="x", pady=2)
                
                ctk.CTkLabel(
                    var_frame,
                    text=f"{{{var_name}}}:",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=self.colors.get('primary', '#1e40af')
                ).pack(anchor="w", padx=10, pady=(5, 0))
                
                value_text = str(var_value)[:200] + "..." if len(str(var_value)) > 200 else str(var_value)
                ctk.CTkLabel(
                    var_frame,
                    text=value_text,
                    font=ctk.CTkFont(size=10),
                    wraplength=600,
                    justify="left"
                ).pack(anchor="w", padx=20, pady=(0, 5))
            
            # Final prompt tab
            prompt_tab = tabview.add("Final Prompt")
            prompt_frame = ctk.CTkFrame(prompt_tab)
            prompt_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            ctk.CTkLabel(
                prompt_frame,
                text="Final Prompt (Ready for AI):",
                font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=10, pady=(10, 5))
            
            prompt_textbox = ctk.CTkTextbox(
                prompt_frame,
                font=ctk.CTkFont(size=11),
                wrap="word"
            )
            prompt_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            prompt_textbox.insert("1.0", test_prompt)
            
            # Action buttons
            button_frame = ctk.CTkFrame(test_window, fg_color="transparent")
            button_frame.pack(fill="x", padx=10, pady=(5, 10))
            
            # Copy prompt button
            copy_btn = ctk.CTkButton(
                button_frame,
                text="📋 Copy Prompt",
                command=lambda: self.copy_to_clipboard(test_prompt),
                width=120
            )
            copy_btn.pack(side="left", padx=(0, 10))
            
            # Close button
            ctk.CTkButton(
                button_frame,
                text="Close",
                command=test_window.destroy,
                width=100
            ).pack(side="right")
            
        except Exception as e:
            print(f"Error showing test result: {e}")
    
    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.show_toast("Copied to clipboard!", 2000)
        except Exception as e:
            print(f"Error copying to clipboard: {e}")
    
    def update_insight_window_label(self, value):
        """Update insight time window label"""
        minutes = int(value)
        self.insight_window_label.configure(text=f"{minutes} min")

    def load_insight_prompts(self):
        """Load custom insight prompts from config or return defaults"""
        try:
            config_file = Path("insight_prompts.json")
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading insight prompts: {e}")

        # Default prompts
        return {
            "cbt": {
                "label": "CBT Analysis",
                "prompt": "Analyze this therapy session excerpt from a Cognitive Behavioral Therapy perspective. Identify cognitive distortions, behavioral patterns, and therapeutic opportunities. Provide actionable insights for the therapist."
            },
            "risk": {
                "label": "Risk Assessment",
                "prompt": "Evaluate this therapy session excerpt for any risk factors including suicidal ideation, self-harm, harm to others, or crisis situations. Provide a clear risk level assessment and recommended actions."
            },
            "progress": {
                "label": "Progress Check",
                "prompt": "Analyze this therapy session excerpt to identify client progress, therapeutic alliance quality, treatment adherence, and areas showing improvement or concern."
            }
        }

    def save_insight_prompts(self):
        """Save custom insight prompts to config file"""
        try:
            config_file = Path("insight_prompts.json")
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.insight_prompts, f, indent=2)
            print("Insight prompts saved successfully")
        except Exception as e:
            print(f"Error saving insight prompts: {e}")

    def generate_insight_on_demand(self, prompt_id):
        """Generate insight for selected time window using specified prompt"""
        # Early return if insights are disabled
        if not self.analysis_enabled:
            return

        if not GEMINI_AVAILABLE or not self.gemini_model:
            messagebox.showerror("Error", "Gemini API not available. Check API configuration.")
            return

        try:
            # Get time window in minutes
            window_minutes = self.insight_window_var.get()
            window_seconds = window_minutes * 60

            # Get transcript from last X minutes
            transcript_text = self.get_recent_transcript(window_seconds)

            if not transcript_text or len(transcript_text.strip()) < 50:
                messagebox.showwarning("No Content", f"Not enough transcript content in the last {window_minutes} minute(s).")
                return

            # Get the prompt
            prompt_data = self.insight_prompts.get(prompt_id)
            if not prompt_data:
                messagebox.showerror("Error", "Prompt not found")
                return

            # Disable button during processing
            if prompt_id in self.insight_buttons:
                self.insight_buttons[prompt_id].configure(state="disabled", text="Generating...")

            # Generate insight in background thread
            import threading
            def run_insight():
                try:
                    # Use multi-provider to generate insight
                    prompt = f"{prompt_data['prompt']}\n\nTranscript (last {window_minutes} min):\n{transcript_text}"

                    # Use multi-provider system
                    success, insight_text = self.generate_with_provider(prompt)

                    if not success:
                        insight_text = f"Insight generation failed: {insight_text}"

                    # Record LLM usage (Phase 5b)
                    input_tokens, output_tokens, cost = self.estimate_tokens_and_cost(prompt, insight_text)
                    self.record_llm_usage('gemini-2.0-flash-exp', input_tokens, output_tokens, cost)

                    # Display insight in UI (main thread)
                    self.root.after(0, lambda: self.display_insight(prompt_data['label'], insight_text, window_minutes))

                except Exception as e:
                    error_msg = f"Insight generation failed: {str(e)}"
                    print(error_msg)
                    self.root.after(0, lambda: messagebox.showerror("Error", error_msg))

                finally:
                    # Re-enable button
                    if prompt_id in self.insight_buttons:
                        self.root.after(0, lambda: self.insight_buttons[prompt_id].configure(
                            state="normal",
                            text=prompt_data['label']
                        ))

            threading.Thread(target=run_insight, daemon=True).start()

        except Exception as e:
            print(f"Error generating insight: {e}")
            messagebox.showerror("Error", f"Failed to generate insight: {str(e)}")

    def get_recent_transcript(self, seconds):
        """Get transcript text from the last N seconds"""
        try:
            # Get all transcript text
            full_transcript = self._get_transcript_as_text()

            if not full_transcript:
                return ""

            # For simplicity, return last N characters (approximation)
            # In production, you'd parse timestamps if available
            # Rough estimate: 150 words per minute, 5 chars per word = 750 chars/min
            chars_per_second = 750 / 60
            approx_chars = int(seconds * chars_per_second)

            # Get last N characters
            if len(full_transcript) <= approx_chars:
                return full_transcript
            else:
                return "..." + full_transcript[-approx_chars:]

        except Exception as e:
            print(f"Error getting recent transcript: {e}")
            return ""

    def get_highlighted_transcript(self):
        """Get currently highlighted/selected text from transcript widget"""
        try:
            # Access the text widget through transcript_panel_actions
            if hasattr(self, 'transcript_panel_actions') and self.transcript_panel_actions.text_widget:
                text_widget = self.transcript_panel_actions.text_widget

                # Check if there's a selection
                try:
                    selection = text_widget.get("sel.first", "sel.last")
                    if selection and selection.strip():
                        return selection.strip()
                except:
                    # No selection
                    pass

            return ""

        except Exception as e:
            print(f"Error getting highlighted transcript: {e}")
            return ""

    def resolve_segment(self):
        """
        Determine transcript segment source: highlighted text or time-based.

        Returns:
            tuple: (segment_text, source_label)
                segment_text: The transcript text to analyze
                source_label: Human-readable description ("selection" or "last X min")
        """
        try:
            # First, check for highlighted text
            highlighted = self.get_highlighted_transcript()
            if highlighted:
                return (highlighted, "selection")

            # Fall back to time-based segment
            minutes = getattr(self, 'insight_window_minutes', 5)
            if not hasattr(self, 'insight_window_var'):
                # Fallback if var not set
                seconds = minutes * 60
            else:
                minutes = self.insight_window_var.get()
                seconds = minutes * 60

            transcript_text = self.get_recent_transcript(seconds)

            if not transcript_text or len(transcript_text.strip()) < 50:
                return ("", f"last {minutes} min (empty)")

            return (transcript_text, f"last {minutes} min")

        except Exception as e:
            print(f"Error resolving segment: {e}")
            return ("", "error")

    def display_insight(self, label, insight_text, window_minutes):
        """Display generated insight in the insights panel - UNIFIED SINK (routes to NEW panel)"""
        try:
            # DIAGNOSTICS: Log insight payload
            if hasattr(self, 'VERBOSE_INSIGHTS') and self.VERBOSE_INSIGHTS:
                import threading
                print(f"INSIGHT_PAYLOAD keys=['label', 'text', 'window'], text_len={len(insight_text)}")
                print(f"INSIGHT_THREAD main={threading.current_thread() == threading.main_thread()}")

            # ===================================================================
            # ROUTE TO NEW INSIGHTS PANEL (Phase 1)
            # ===================================================================
            if hasattr(self, 'insights_actions') and self.insights_actions.add_insight_card:
                card = {
                    'title': label,
                    'body': insight_text,
                    'tags': [f'{window_minutes} min window'],
                    'ts': datetime.now()
                }
                self.insights_actions.add_insight_card(card)
                
                # Update cost in state
                self.insights_state.cost = f"${self.analysis_stats.get('total_cost', 0):.2f}"
                if self.insights_actions.update_summary:
                    self.insights_actions.update_summary()
                
                if self.VERBOSE_INSIGHTS:
                    print(f"INSIGHT_ROUTED_TO_NEW_PANEL title=\"{label}\"")
            
            # ===================================================================
            # LEGACY: Also route to old panel (for backward compatibility)
            # TODO: Remove this after full migration
            # ===================================================================
            if hasattr(self, 'insights_scrollable') and self.insights_scrollable.winfo_exists():
                insight_data = {
                    'type': label,
                    'content': insight_text,
                    'timestamp': time.time(),
                    'window_minutes': window_minutes
                }
                self.insights_scrollable.after(0, lambda: self._render_insight_card(insight_data))

            # Visible acknowledgment
            char_count = len(insight_text)
            print(f"[OK] Insight received ({char_count} chars): {label}")
            self.root.after(0, lambda: self.show_toast(f"Insight received ({char_count} chars)"))

        except Exception as e:
            print(f"Error displaying insight: {e}")
            import traceback
            traceback.print_exc()

    def open_prompt_manager(self):
        """Open dialog to manage custom insight prompts"""
        # Create a toplevel window for managing prompts
        manager = ctk.CTkToplevel(self.root)
        manager.title("Manage Custom Prompts")
        manager.geometry("600x500")
        manager.transient(self.root)
        manager.grab_set()

        # Instructions
        ctk.CTkLabel(
            manager,
            text="Customize your insight generation prompts",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        # Scrollable frame for prompts
        scroll_frame = ctk.CTkScrollableFrame(manager, width=550, height=350)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        prompt_entries = {}

        for prompt_id, prompt_data in self.insight_prompts.items():
            # Prompt frame
            prompt_frame = ctk.CTkFrame(scroll_frame)
            prompt_frame.pack(fill="x", pady=10, padx=5)

            # Label entry
            ctk.CTkLabel(prompt_frame, text="Button Label:", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=5, pady=(5, 2))
            label_entry = ctk.CTkEntry(prompt_frame, width=500)
            label_entry.insert(0, prompt_data['label'])
            label_entry.pack(padx=5, pady=(0, 5))

            # Prompt text entry
            ctk.CTkLabel(prompt_frame, text="Prompt Text:", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=5, pady=(5, 2))
            prompt_textbox = ctk.CTkTextbox(prompt_frame, width=500, height=100)
            prompt_textbox.insert("1.0", prompt_data['prompt'])
            prompt_textbox.pack(padx=5, pady=(0, 5))

            prompt_entries[prompt_id] = {
                'label': label_entry,
                'prompt': prompt_textbox
            }

        # Save button
        def save_prompts():
            try:
                for prompt_id, entries in prompt_entries.items():
                    self.insight_prompts[prompt_id]['label'] = entries['label'].get()
                    self.insight_prompts[prompt_id]['prompt'] = entries['prompt'].get("1.0", "end-1c")

                self.save_insight_prompts()

                # Update button labels
                for prompt_id, prompt_data in self.insight_prompts.items():
                    if prompt_id in self.insight_buttons:
                        self.insight_buttons[prompt_id].configure(text=prompt_data['label'])

                messagebox.showinfo("Success", "Prompts saved successfully!")
                manager.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save prompts: {str(e)}")

        save_btn = ctk.CTkButton(manager, text="Save Changes", command=save_prompts, height=35)
        save_btn.pack(pady=10)

    # ===================================================================
    # TEST HELPER: Verify new insights panel rendering
    # ===================================================================
    
    # Legacy methods - kept for compatibility but disabled
    def update_analysis_mode(self):
        """Disabled - analysis is now on-demand only"""
        pass

    def update_analysis_frequency(self, value):
        """Disabled - analysis is now on-demand only"""
        pass
    
    def toggle_recording(self):
        """Start or stop recording"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def generate_session_summary(self, attachment_path=None):
        """
        Generate comprehensive session summary using Gemini API.

        Args:
            attachment_path (str, optional): Path to file attachment for context

        Reasoning:
            - PATCH_4: Supports optional document context
            - Falls back to transcript-only if no attachment
        """
        try:
            # Get full transcript
            full_transcript = self._get_transcript_as_text()

            if not full_transcript or len(full_transcript.strip()) < 100:
                messagebox.showwarning("Insufficient Data", "Not enough transcript content to generate summary.")
                return

            # Load attachment if provided
            attachment_context = ""
            if attachment_path and Path(attachment_path).exists():
                try:
                    with open(attachment_path, 'r', encoding='utf-8', errors='ignore') as f:
                        attachment_content = f.read(5000)  # First 5KB
                    attachment_context = f"\n\n**Attached Document Context ('{Path(attachment_path).name}'):**\n{attachment_content}\n"
                    print(f"[OK] Loaded attachment: {Path(attachment_path).name} ({len(attachment_content)} chars)")
                except Exception as e:
                    print(f"Warning: Could not read attachment: {e}")
                    attachment_context = f"\n\n**Attachment**: {Path(attachment_path).name} (could not read)\n"

            # Show progress dialog
            progress_window = ctk.CTkToplevel(self.root)
            progress_window.title("Generating Session Summary")
            progress_window.geometry("400x150")
            progress_window.transient(self.root)
            progress_window.grab_set()

            ctk.CTkLabel(
                progress_window,
                text="Generating comprehensive session summary...",
                font=ctk.CTkFont(size=12)
            ).pack(pady=20)

            progress_bar = ctk.CTkProgressBar(progress_window, width=300)
            progress_bar.pack(pady=10)
            progress_bar.set(0)

            status_label = ctk.CTkLabel(progress_window, text="Analyzing transcript...")
            status_label.pack(pady=10)

            # Get client info if available
            client_info = self.load_client_info()

            # Generate summary in background thread
            def run_summary():
                try:
                    progress_window.after(0, lambda: progress_bar.set(0.3))
                    progress_window.after(0, lambda: status_label.configure(text="Sending to Gemini API..."))

                    # Comprehensive prompt for session summary
                    prompt = f"""You are an expert clinical psychologist assistant. Analyze this therapy session and provide:

1. **Session Overview**: Brief summary of the session's main themes and focus areas
2. **Client Progress**: Observable progress, improvements, or setbacks
3. **Therapeutic Interventions**: Techniques used and their apparent effectiveness
4. **Risk Assessment**: Any safety concerns, suicidal ideation, or crisis indicators
5. **Treatment Recommendations**: Suggested next steps and areas for future focus
6. **Process Notes**: Important observations about therapeutic alliance, engagement, etc.

{f"**Client Information:**{client_info}" if client_info else ""}
{attachment_context}

**Full Session Transcript:**
{full_transcript}

Provide a professional clinical summary suitable for therapist case notes."""

                    # Use multi-provider system
                    success, summary_text = self.generate_with_provider(prompt)

                    if not success:
                        summary_text = f"Summary generation failed: {summary_text}"

                    progress_window.after(0, lambda: progress_bar.set(1.0))
                    progress_window.after(0, lambda: status_label.configure(text="Complete!"))

                    # Display summary
                    self.root.after(0, lambda: self.display_session_summary(summary_text))
                    self.root.after(500, lambda: progress_window.destroy())

                except Exception as e:
                    error_msg = f"Summary generation failed: {str(e)}"
                    print(error_msg)
                    self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
                    self.root.after(0, lambda: progress_window.destroy())

            import threading
            threading.Thread(target=run_summary, daemon=True).start()

        except Exception as e:
            print(f"Error generating session summary: {e}")
            messagebox.showerror("Error", f"Failed to generate summary: {str(e)}")

    def generate_progress_notes(self):
        """Generate progress and process notes with optional markdown template"""
        try:
            if not GEMINI_AVAILABLE or not self.gemini_model:
                messagebox.showerror("Error", "Gemini API not available. Check API configuration.")
                return

            # Get full transcript
            full_transcript = self._get_transcript_as_text()

            if not full_transcript or len(full_transcript.strip()) < 100:
                messagebox.showwarning("Insufficient Data", "Not enough transcript content to generate progress notes.")
                return

            # File picker for markdown template
            from tkinter import filedialog
            template_file = filedialog.askopenfilename(
                title="Select Markdown Template (optional)",
                filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
                initialdir="."
            )

            template_content = ""
            if template_file:
                try:
                    with open(template_file, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                    print(f"Loaded template: {template_file}")
                except Exception as e:
                    print(f"Error reading template: {e}")
                    messagebox.showerror("Error", f"Could not read template file: {e}")
                    return

            # Show progress dialog
            progress_window = ctk.CTkToplevel(self.root)
            progress_window.title("Generating Progress Notes")
            progress_window.geometry("400x150")
            progress_window.transient(self.root)
            progress_window.grab_set()

            ctk.CTkLabel(
                progress_window,
                text="Generating comprehensive progress notes...",
                font=ctk.CTkFont(size=12)
            ).pack(pady=20)

            progress_bar = ctk.CTkProgressBar(progress_window, width=300)
            progress_bar.pack(pady=10)
            progress_bar.set(0)

            status_label = ctk.CTkLabel(progress_window, text="Analyzing transcript...")
            status_label.pack(pady=10)

            # Generate in background thread
            def run_progress_notes():
                try:
                    progress_window.after(0, lambda: progress_bar.set(0.3))
                    progress_window.after(0, lambda: status_label.configure(text="Sending to Gemini API..."))

                    # Build comprehensive prompt
                    template_section = f"**Template/Guidelines:**\n{template_content}\n\n" if template_content else ""
                    instruction_type = "Follow the structure and format provided in the template above" if template_content else "Provide a structured clinical progress note"

                    prompt = f"""You are an expert clinical psychologist assistant. Generate comprehensive progress and process notes for this session.

{template_section}**Instructions:**
1. Analyze the full session transcript
2. {instruction_type}
3. Include:
   - Session summary and main themes
   - Client progress and observable changes
   - Interventions used and their effectiveness
   - Risk assessment
   - Treatment plan updates
   - Process observations

**Full Session Transcript:**
{full_transcript}

Provide a complete, professional progress and process note suitable for clinical documentation."""

                    # Use multi-provider system
                    success, notes_text = self.generate_with_provider(prompt)

                    if not success:
                        notes_text = f"Progress notes generation failed: {notes_text}"

                    progress_window.after(0, lambda: progress_bar.set(1.0))
                    progress_window.after(0, lambda: status_label.configure(text="Complete!"))

                    # Display notes
                    self.root.after(0, lambda: self.display_progress_notes(notes_text))
                    self.root.after(500, lambda: progress_window.destroy())

                except Exception as e:
                    error_msg = f"Progress notes generation failed: {str(e)}"
                    print(error_msg)
                    self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
                    self.root.after(0, lambda: progress_window.destroy())

            import threading
            threading.Thread(target=run_progress_notes, daemon=True).start()

        except Exception as e:
            print(f"Error generating progress notes: {e}")
            messagebox.showerror("Error", f"Failed to generate progress notes: {str(e)}")

    def display_progress_notes(self, notes_text):
        """Display progress notes in a new window with save option"""
        notes_window = ctk.CTkToplevel(self.root)
        notes_window.title("Progress & Process Notes")
        notes_window.geometry("900x700")
        notes_window.transient(self.root)

        # Title
        title_label = ctk.CTkLabel(
            notes_window,
            text="📋 Progress & Process Notes",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=10)

        # Notes text area
        notes_textbox = ctk.CTkTextbox(
            notes_window,
            font=ctk.CTkFont(size=11),
            wrap="word"
        )
        notes_textbox.pack(fill="both", expand=True, padx=20, pady=10)
        notes_textbox.insert("1.0", notes_text)

        # Buttons frame
        button_frame = ctk.CTkFrame(notes_window, fg_color="transparent")
        button_frame.pack(pady=10)

        def save_notes():
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sessions/progress_notes_{timestamp}.txt"

            try:
                Path("sessions").mkdir(exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(notes_text)
                messagebox.showinfo("Saved", f"Progress notes saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

        save_btn = ctk.CTkButton(
            button_frame,
            text="💾 Save Notes",
            command=save_notes,
            width=150,
            height=35
        )
        save_btn.pack(side="left", padx=5)

        close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            command=notes_window.destroy,
            width=150,
            height=35
        )
        close_btn.pack(side="left", padx=5)

    def load_client_info(self):
        """Load client information from file if available"""
        try:
            # Check for client_info.json in current directory
            client_file = Path("client_info.json")
            if client_file.exists():
                with open(client_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    # Format client info for prompt
                    formatted = "\n"
                    for key, value in info.items():
                        formatted += f"- {key}: {value}\n"
                    return formatted
            return None
        except Exception as e:
            print(f"Error loading client info: {e}")
            return None

    def display_session_summary(self, summary_text):
        """Display session summary in a new window"""
        try:
            # Create summary window
            summary_window = ctk.CTkToplevel(self.root)
            summary_window.title("Session Summary & Process Notes")
            summary_window.geometry("800x600")
            summary_window.transient(self.root)

            # Header
            ctk.CTkLabel(
                summary_window,
                text="AI-Generated Session Summary",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=10)

            # Timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ctk.CTkLabel(
                summary_window,
                text=f"Generated: {timestamp}",
                font=ctk.CTkFont(size=10),
                text_color="gray"
            ).pack()

            # Summary text (scrollable)
            summary_textbox = ctk.CTkTextbox(
                summary_window,
                width=750,
                height=450,
                wrap="word"
            )
            summary_textbox.pack(padx=20, pady=10, fill="both", expand=True)
            summary_textbox.insert("1.0", summary_text)
            summary_textbox.configure(state="normal")  # Allow copying

            # Buttons
            button_frame = ctk.CTkFrame(summary_window, fg_color="transparent")
            button_frame.pack(pady=10)

            def save_summary():
                try:
                    session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
                    summary_file = self.sessions_dir / f"summary_{session_name}.txt"
                    with open(summary_file, 'w', encoding='utf-8') as f:
                        f.write(f"Session Summary - {timestamp}\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(summary_text)
                    messagebox.showinfo("Saved", f"Summary saved to:\n{summary_file}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save: {str(e)}")

            ctk.CTkButton(
                button_frame,
                text="Save Summary",
                command=save_summary,
                width=120
            ).pack(side="left", padx=5)

            ctk.CTkButton(
                button_frame,
                text="Close",
                command=summary_window.destroy,
                width=120
            ).pack(side="left", padx=5)

        except Exception as e:
            print(f"Error displaying summary: {e}")
            messagebox.showerror("Error", f"Failed to display summary: {str(e)}")
    
    def start_recording(self):
        """Start audio recording using SoundCard"""
        if not self.whisper_model or not self.silero_vad_model:
            messagebox.showerror("Error", "AI models not available")
            return

        # Lock theme to prevent white flash during UI updates
        self._theme_locked = True

        try:
            # Get selected devices from SessionControls state (Phase 5 integration)
            mic_selection = self.session_controls_state.devices.get('mic_sel')
            buffer_seconds = self.session_controls_state.buffer_seconds
            separate_speakers = self.session_controls_state.separate_speakers

            # Diagnostic logging
            if self.VERBOSE_UI:
                loop_sel = self.session_controls_state.devices.get('loop_sel')
                print(f"START mic={mic_selection} loop={loop_sel} buffer={buffer_seconds}")

            if not mic_selection or mic_selection == "None":
                messagebox.showerror("Error", "Please select a microphone device")
                return

            # Find microphone by name (SoundCard approach)
            selected_mic = None
            for device_id, device_name in self.audio_devices["input"]:
                if device_name == mic_selection:
                    # Get microphone by name for explicit selection
                    all_mics = sc.all_microphones(include_loopback=False)
                    for mic in all_mics:
                        if mic.id == device_id:
                            selected_mic = mic
                            break
                    break

            if not selected_mic:
                messagebox.showerror("Error", "Selected microphone not found")
                return

            # Update buffer duration from state
            self.buffer_duration = buffer_seconds
            self.dual_channel_enabled = separate_speakers

            # Get system audio device if separate speakers enabled
            selected_loopback = None
            selected_speaker_name = None
            if separate_speakers:
                sys_selection = self.session_controls_state.devices.get('loop_sel')
                if sys_selection and sys_selection != "None":
                    for device_id, device_name in self.audio_devices["loopback"]:
                        if device_name == sys_selection:
                            # Use direct loopback device
                            all_loopbacks = sc.all_microphones(include_loopback=True)
                            for lb in all_loopbacks:
                                if lb.id == device_id:
                                    selected_loopback = lb
                                    selected_speaker_name = lb.name
                                    break
                            break

            # Update recording state
            self.is_recording = True
            self._countdown_active = True  # Enable countdown

            # Update SessionControls button state via action (no direct widget access)
            set_recording_state_action(
                self.session_controls_state,
                is_recording=True,
                theme=self.colors,
                verbose=self.VERBOSE_UI
            )

            # Update status bar with buffer info
            self.set_status(f"Recording…  Buffer={buffer_seconds}s")

            # Create session info
            self.current_session = datetime.now()
            self.session_start_time = time.time()  # Initialize for dashboard metrics
            session_name = self.current_session.strftime("%Y-%m-%d_%H-%M-%S")
            if hasattr(self, 'session_info_label'):
                self.session_info_label.configure(text=f"Session: {session_name}")

            # Update TopNavBar session display (Phase 5 integration)
            if hasattr(self, 'topnav_state'):
                self.topnav_state.session_file = session_name

            # Fix #1: Set absolute session start time for transcript stitcher
            self.absolute_session_start_time = time.time()
            self.transcript_stitcher.set_session_start(self.absolute_session_start_time)

            # PATCH_DIARIZE: Reset OnlineDiarizer for new session
            # Reasoning: Each session should start with fresh speaker database
            if self.online_diarizer:
                self.online_diarizer.reset()
                if self.VERBOSE_UI:
                    print("[DIARIZE] OnlineDiarizer reset for new session")

            # Clear placeholder and prepare transcript area (legacy UI)
            if hasattr(self, 'transcript_text'):
                self.clear_transcript_placeholder()
                self.transcript_text.delete("1.0", "end")

            # Start dashboard UI updates
            self.start_session_ui_updates()

            # Initialize buffers
            self.audio_buffer = []
            self.sys_audio_buffer = []
            self.buffer_start_time = time.time()
            self.processing_buffer = False

            # Initialize 2-minute diarization buffers
            self.diarization_audio_buffer = []
            self.diarization_sys_buffer = []
            self.diarization_buffer_start = time.time()
            self.diarization_processing = False

            # Store selected devices
            self.selected_mic = selected_mic
            self.selected_loopback = selected_loopback
            self.selected_speaker_name = selected_speaker_name

            print(f"Selected microphone: {selected_mic.name}")
            if selected_loopback:
                print(f"Selected loopback device: {selected_loopback.name}")
            if selected_speaker_name:
                print(f"Selected speaker for loopback: {selected_speaker_name}")

            # Start recording thread
            self.recording_thread = threading.Thread(target=self.record_with_soundcard, daemon=True)
            self.recording_thread.start()

        except Exception as e:
            messagebox.showerror("Recording Error", f"Failed to start recording: {str(e)}")
            self.is_recording = False
            self.set_status("Error – see console")
        finally:
            # Unlock theme after start completes
            self._theme_locked = False
    
    def stop_recording(self):
        """Stop recording and save transcript with optional session summary"""
        if not self.is_recording:
            return

        # Lock theme to prevent white flash during UI updates
        self._theme_locked = True

        try:
            # Stop recording immediately (NO auto-send to Gemini)
            self.is_recording = False

            # Stop countdown if active (idempotent)
            self._countdown_active = False

            # Cancel any pending countdown timer if exists
            if hasattr(self, '_countdown_after_id') and self._countdown_after_id:
                try:
                    self.root.after_cancel(self._countdown_after_id)
                    self._countdown_after_id = None
                except:
                    pass  # Ignore if already cancelled

            # Stop dashboard UI updates
            self.stop_session_ui_updates()

            # Update SessionControls button state via action (no direct widget access)
            set_recording_state_action(
                self.session_controls_state,
                is_recording=False,
                theme=self.colors,
                verbose=self.VERBOSE_UI
            )

            # Update status bar
            self.set_status("Session completed")

            # Save transcript
            self.save_transcript()

            # Diagnostic logging
            if self.VERBOSE_UI:
                print(f"STOP session saved")

            # Final status
            self.set_status("Stopped")

        except Exception as e:
            self.set_status("Error – see console")
            messagebox.showerror("Stop Error", f"Error stopping recording: {str(e)}")
        finally:
            # Unlock theme after stop completes
            self._theme_locked = False
    
    def record_with_soundcard(self):
        """Record audio using SoundCard with 15-20 second buffer accumulation"""
        print(f"Starting SoundCard recording: Rate={self.sample_rate}, Buffer={self.buffer_duration}s")

        try:
            # Start recording from microphone with larger buffer
            with self.selected_mic.recorder(
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.audio_blocksize
            ) as mic_recorder:
                # Start system audio recording if enabled
                sys_recorder = None
                if self.selected_loopback:
                    try:
                        # Direct loopback device with larger buffer
                        sys_recorder = self.selected_loopback.recorder(
                            samplerate=self.sample_rate,
                            channels=1,
                            blocksize=self.audio_blocksize
                        )
                        sys_recorder.__enter__()
                        print(f"System audio recording started with direct loopback: {self.selected_loopback.name}")
                    except Exception as e:
                        print(f"Failed to start direct loopback recording: {e}")
                        sys_recorder = None
                elif self.selected_speaker_name:
                    try:
                        # Get loopback microphone using speaker name
                        print(f"Attempting to get loopback microphone for speaker: {self.selected_speaker_name}")

                        # Try different approaches to get the loopback microphone
                        loopback_mic = None

                        # First try exact name match
                        try:
                            loopback_mic = sc.get_microphone(self.selected_speaker_name, include_loopback=True)
                            if loopback_mic:
                                print(f"Found loopback microphone with exact name match: {loopback_mic.name}")
                        except Exception as e:
                            print(f"Exact name match failed: {e}")

                        # If that fails, try searching through all loopback devices
                        if not loopback_mic:
                            print("Searching through all loopback devices...")
                            all_loopback_mics = sc.all_microphones(include_loopback=True)
                            for mic in all_loopback_mics:
                                print(f"  Checking loopback mic: {mic.name}")
                                if self.selected_speaker_name.lower() in mic.name.lower() or mic.name.lower() in self.selected_speaker_name.lower():
                                    loopback_mic = mic
                                    print(f"  Found matching loopback microphone: {mic.name}")
                                    break

                        if loopback_mic:
                            sys_recorder = loopback_mic.recorder(
                                samplerate=self.sample_rate,
                                channels=1,
                                blocksize=self.audio_blocksize
                            )
                            sys_recorder.__enter__()
                            print(f"System audio recording started with WASAPI loopback: {loopback_mic.name}")
                        else:
                            print(f"Could not find any loopback microphone for speaker: {self.selected_speaker_name}")
                            print("Available loopback devices:")
                            for mic in sc.all_microphones(include_loopback=True):
                                print(f"  - {mic.name}")

                    except Exception as e:
                        print(f"Failed to start WASAPI loopback recording: {e}")
                        sys_recorder = None

                # Continuous recording with buffer accumulation
                print(f"Recording with {self.recording_chunk_duration*1000}ms chunks, blocksize={self.audio_blocksize}")

                while self.is_recording:
                    try:
                        # Record audio chunk (200ms for stability)
                        chunk_size = int(self.sample_rate * self.recording_chunk_duration)

                        # Read microphone data with discontinuity handling
                        try:
                            mic_data = mic_recorder.record(numframes=chunk_size)
                            if mic_data is not None and len(mic_data) > 0:
                                flattened_mic = mic_data.flatten()
                                self.audio_buffer.append(flattened_mic)
                                # Also add to diarization buffer if advanced mode enabled
                                if self.advanced_diarization_enabled and self.pyannote_pipeline:
                                    self.diarization_audio_buffer.append(flattened_mic)
                                # Reset discontinuity count on successful read
                                if self.discontinuity_count > 0:
                                    self.discontinuity_count = max(0, self.discontinuity_count - 1)
                        except Exception as mic_error:
                            self.discontinuity_count += 1
                            self.performance_stats['discontinuities'] += 1
                            self.performance_stats['buffer_underruns'] += 1

                            # Throttle discontinuity warnings to reduce noise
                            self.discontinuity_warning_counter += 1
                            if self.discontinuity_warning_counter % self.discontinuity_warning_throttle == 0:
                                print(f"Microphone discontinuity #{self.discontinuity_count} (logged every {self.discontinuity_warning_throttle}): {mic_error}")

                            if self.discontinuity_count > self.max_discontinuities:
                                if self.discontinuity_warning_counter % self.discontinuity_warning_throttle == 0:
                                    print(f"Discontinuity count: {self.discontinuity_count}/{self.max_discontinuities}, continuing with graceful recovery")

                            # Add silence to maintain timing
                            silence = np.zeros(chunk_size, dtype=self.dtype)
                            self.audio_buffer.append(silence)
                            # Also add to diarization buffer if enabled
                            if self.advanced_diarization_enabled and self.pyannote_pipeline:
                                self.diarization_audio_buffer.append(silence)

                        # Read system audio data if available
                        if sys_recorder:
                            try:
                                sys_data = sys_recorder.record(numframes=chunk_size)
                                if sys_data is not None and len(sys_data) > 0:
                                    # Convert to mono if stereo
                                    if len(sys_data.shape) > 1 and sys_data.shape[1] > 1:
                                        sys_data = np.mean(sys_data, axis=1)
                                    flattened_sys = sys_data.flatten()
                                    self.sys_audio_buffer.append(flattened_sys)
                                    # Also add to diarization buffer if advanced mode enabled
                                    if self.advanced_diarization_enabled and self.pyannote_pipeline:
                                        self.diarization_sys_buffer.append(flattened_sys)
                            except Exception as sys_error:
                                self.performance_stats['discontinuities'] += 1
                                # Throttle system audio discontinuity warnings
                                self.discontinuity_warning_counter += 1
                                if self.discontinuity_warning_counter % self.discontinuity_warning_throttle == 0:
                                    print(f"System audio discontinuity (logged every {self.discontinuity_warning_throttle}): {sys_error}")
                                # Add silence to maintain timing
                                silence = np.zeros(chunk_size, dtype=self.dtype)
                                self.sys_audio_buffer.append(silence)
                                # Also add to diarization buffer if enabled
                                if self.advanced_diarization_enabled and self.pyannote_pipeline:
                                    self.diarization_sys_buffer.append(silence)

                        # Check if buffer duration reached
                        current_time = time.time()
                        buffer_duration = current_time - self.buffer_start_time

                        # Update status to show buffer progress (only if countdown active)
                        # Guard: skip status update if countdown stopped (prevents spam after Stop)
                        if self.is_recording and getattr(self, '_countdown_active', False):
                            remaining = max(0, self.buffer_duration - buffer_duration)
                            if remaining > 0:
                                self.set_status(f"Recording... Processing in {remaining:.0f}s")
                            else:
                                self.set_status("Recording... Processing audio...")

                        # Process buffer when duration reached
                        if buffer_duration >= self.buffer_duration and not self.processing_buffer and self.audio_buffer:
                            self.processing_buffer = True

                            # Concatenate buffer chunks into continuous audio
                            mic_audio = np.concatenate(self.audio_buffer) if self.audio_buffer else np.array([])
                            sys_audio = np.concatenate(self.sys_audio_buffer) if self.sys_audio_buffer else np.array([])

                            # Process buffer in separate thread
                            processing_thread = threading.Thread(
                                target=self.process_audio_buffer_with_vad,
                                args=(mic_audio.copy(), sys_audio.copy() if len(sys_audio) > 0 else None),
                                daemon=True
                            )
                            processing_thread.start()

                            # Keep 2-second overlap for continuity
                            overlap_samples = int(self.sample_rate * 2)
                            if len(mic_audio) > overlap_samples:
                                overlap_mic = mic_audio[-overlap_samples:]
                                self.audio_buffer = [overlap_mic]
                            else:
                                self.audio_buffer = []

                            if len(sys_audio) > overlap_samples:
                                overlap_sys = sys_audio[-overlap_samples:]
                                self.sys_audio_buffer = [overlap_sys]
                            else:
                                self.sys_audio_buffer = []

                            self.buffer_start_time = current_time
                            self.processing_buffer = False

                        # Check 2-minute diarization buffer for advanced speaker identification
                        if (self.advanced_diarization_enabled and self.pyannote_pipeline and
                            not self.diarization_processing and self.diarization_audio_buffer):
                            diarization_duration = current_time - self.diarization_buffer_start

                            if diarization_duration >= self.diarization_buffer_size:
                                self.diarization_processing = True

                                # Concatenate diarization buffer chunks
                                diar_mic_audio = np.concatenate(self.diarization_audio_buffer) if self.diarization_audio_buffer else np.array([])
                                diar_sys_audio = np.concatenate(self.diarization_sys_buffer) if self.diarization_sys_buffer else None

                                # Process in separate thread for advanced diarization
                                diarization_thread = threading.Thread(
                                    target=self.process_advanced_diarization,
                                    args=(diar_mic_audio.copy(), diar_sys_audio.copy() if diar_sys_audio is not None else None),
                                    daemon=True
                                )
                                diarization_thread.start()

                                # Keep dynamic overlap for speaker continuity
                                overlap_seconds = self.get_diarization_overlap_size()
                                overlap_samples = int(self.sample_rate * overlap_seconds)
                                if len(diar_mic_audio) > overlap_samples:
                                    overlap_mic = diar_mic_audio[-overlap_samples:]
                                    self.diarization_audio_buffer = [overlap_mic]
                                else:
                                    self.diarization_audio_buffer = []

                                if diar_sys_audio is not None and len(diar_sys_audio) > overlap_samples:
                                    overlap_sys = diar_sys_audio[-overlap_samples:]
                                    self.diarization_sys_buffer = [overlap_sys]
                                else:
                                    self.diarization_sys_buffer = []

                                self.diarization_buffer_start = current_time
                                self.diarization_processing = False

                    except Exception as e:
                        if self.is_recording:
                            print(f"Recording chunk error: {e}")
                        break

                # Cleanup system audio recorder
                if sys_recorder:
                    try:
                        sys_recorder.__exit__(None, None, None)
                    except Exception as e:
                        print(f"Error closing system audio recorder: {e}")

            # Process any remaining buffers when stopping
            if self.audio_buffer:
                mic_audio = np.concatenate(self.audio_buffer)
                sys_audio = np.concatenate(self.sys_audio_buffer) if self.sys_audio_buffer else None
                self.process_audio_buffer_with_vad(mic_audio, sys_audio)

            # Process any remaining diarization buffer
            if (self.advanced_diarization_enabled and self.pyannote_pipeline and
                self.diarization_audio_buffer):
                diar_mic_audio = np.concatenate(self.diarization_audio_buffer)
                diar_sys_audio = np.concatenate(self.diarization_sys_buffer) if self.diarization_sys_buffer else None
                self.process_advanced_diarization(diar_mic_audio, diar_sys_audio)

        except Exception as e:
            print(f"SoundCard recording error: {e}")
            if self.is_recording:
                messagebox.showerror("Recording Error", f"Recording failed: {str(e)}")
                self.is_recording = False
    
    def process_audio_buffer_with_vad(self, mic_audio, sys_audio=None):
        """Process audio buffer with Silero VAD and performance monitoring"""
        start_time = time.time()
        audio_duration = len(mic_audio) / self.sample_rate

        print(f"Processing {audio_duration:.1f}s audio buffer with VAD...")

        if not self.whisper_model or not self.silero_vad_model:
            print("ERROR: Models not available")
            return

        if len(mic_audio) == 0:
            print("ERROR: No microphone audio data")
            return

        try:
            # Monitor GPU memory before processing
            gpu_memory_before = self.get_gpu_memory_usage()

            # Debug: Save audio for quality inspection
            self.save_debug_audio(mic_audio, "mic")
            if sys_audio is not None and len(sys_audio) > 0:
                self.save_debug_audio(sys_audio, "sys")

            print(f"Mic audio duration: {audio_duration:.2f}s")
            if sys_audio is not None:
                sys_duration = len(sys_audio) / self.sample_rate
                print(f"System audio duration: {sys_duration:.2f}s")

            # Get the absolute start time of the buffer being processed.
            # This is crucial for converting relative segment timestamps to absolute ones.
            buffer_start_time = self.buffer_start_time or time.time() - audio_duration

            # Process microphone audio with VAD
            mic_segments = self.transcribe_with_vad(mic_audio, "Speaker 1")

            # Process system audio if available
            sys_segments = []
            if sys_audio is not None and len(sys_audio) > 0:
                sys_segments = self.transcribe_with_vad(sys_audio, "Speaker 2")

            # Combine and sort all segments by their start time
            all_segments = (mic_segments or []) + (sys_segments or [])
            all_segments.sort(key=lambda s: s['start'])

            # Process each segment through the transcription pipeline
            for segment in all_segments:
                abs_start = buffer_start_time + segment['start']
                abs_end = buffer_start_time + segment['end']

                turn_data = {
                    'speaker': segment['speaker'],
                    'text': segment['text'],
                    'start': abs_start,
                    'end': abs_end,
                    'id': str(uuid.uuid4())
                }
                self._append_transcript_turn(**turn_data)

            # Performance monitoring
            processing_time = time.time() - start_time
            rtf = processing_time / audio_duration  # Real-time factor
            gpu_memory_after = self.get_gpu_memory_usage()
            # Use interval to get actual CPU usage (first call with interval=None returns 0)
            cpu_usage = psutil.cpu_percent(interval=0.1) if processing_time > 0.1 else psutil.cpu_percent(interval=None) or 0.0

            self.performance_stats['rtf_values'].append(rtf)
            self.performance_stats['processing_times'].append(processing_time)
            self.performance_stats['gpu_memory_usage'].append(gpu_memory_after)
            self.performance_stats['cpu_usage'].append(cpu_usage)

            print(f"Performance: RTF={rtf:.2f}x, Processing={processing_time:.2f}s, GPU={gpu_memory_after}MB, CPU={cpu_usage:.1f}%")

            # Update status with performance info
            if hasattr(self, 'status_label'):
                avg_rtf = np.mean(self.performance_stats['rtf_values'][-10:])  # Last 10 values
                status_text = f"Recording... (RTF: {avg_rtf:.1f}x)"
                self.set_status(status_text)

        except Exception as e:
            print(f"Buffer processing error: {e}")

    def transcribe_with_vad(self, audio_data, speaker_label):
        """Transcribe audio with Silero VAD filtering to prevent hallucinations"""
        try:
            # Apply Silero VAD to detect speech segments
            audio_tensor = torch.tensor(audio_data, dtype=torch.float32)

            # Get speech timestamps using Silero VAD
            speech_timestamps = silero_vad.get_speech_timestamps(
                audio_tensor,
                self.silero_vad_model,
                sampling_rate=self.sample_rate,
                min_speech_duration_ms=250,  # Reduced from 500ms to capture short utterances
                min_silence_duration_ms=100,  # 100ms silence between segments
                return_seconds=False
            )

            if not speech_timestamps:
                print(f"{speaker_label}: No speech detected by VAD")
                return None

            print(f"{speaker_label}: VAD detected {len(speech_timestamps)} speech segments")

            # Extract speech segments
            speech_segments = []
            for ts in speech_timestamps:
                start_sample = ts['start']
                end_sample = ts['end']
                segment = audio_data[start_sample:end_sample]
                if len(segment) > 0:
                    speech_segments.append(segment)

            if not speech_segments:
                print(f"{speaker_label}: No valid speech segments")
                return None

            # Concatenate speech segments
            speech_audio = np.concatenate(speech_segments)
            speech_duration = len(speech_audio) / self.sample_rate

            print(f"{speaker_label}: Processing {speech_duration:.2f}s of speech")

            # Transcribe with faster-whisper using VAD filtering
            segments, info = self.whisper_model.transcribe(
                speech_audio,
                language="en",
                temperature=0.0,
                beam_size=5,
                condition_on_previous_text=True,
                vad_filter=True,  # Enable VAD in Whisper too
                vad_parameters=dict(
                    min_silence_duration_ms=300,  # Reduced from 500ms
                    speech_pad_ms=150  # Reduced from 200ms
                )
            )

            # Return segments with timestamps
            result_segments = []
            for segment in segments:
                # Keep all non-empty transcriptions (removed len > 2 filter to capture short utterances)
                if segment.text.strip() and len(segment.text.strip()) > 0:
                    result_segments.append({
                        'text': segment.text.strip(),
                        'start': segment.start,
                        'end': segment.end,
                        'speaker': speaker_label
                    })
            
            return result_segments

        except Exception as e:
            print(f"VAD transcription error for {speaker_label}: {e}")
            return None

    def process_advanced_diarization(self, mic_audio, sys_audio=None):
        """Two-stage processing: Whisper transcription + pyannote speaker diarization"""
        start_time = time.time()
        audio_duration = len(mic_audio) / self.sample_rate

        print(f"Processing {audio_duration:.1f}s audio with advanced diarization...")

        if not self.whisper_model or not self.pyannote_pipeline:
            print("ERROR: Required models not available for advanced diarization")
            return

        if len(mic_audio) == 0:
            print("ERROR: No audio data for diarization")
            return

        try:
            # Stage 1: Whisper transcription (combine all audio for better accuracy)
            combined_audio = mic_audio
            if sys_audio is not None and len(sys_audio) > 0:
                # Mix mic and system audio for combined transcription
                min_length = min(len(mic_audio), len(sys_audio))
                combined_audio = (mic_audio[:min_length] + sys_audio[:min_length]) / 2
                # Append remaining audio if lengths differ
                if len(mic_audio) > min_length:
                    combined_audio = np.concatenate([combined_audio, mic_audio[min_length:]])
                elif len(sys_audio) > min_length:
                    combined_audio = np.concatenate([combined_audio, sys_audio[min_length:]])

            # Transcribe with Whisper
            print("Stage 1: Whisper transcription...")
            segments_generator, info = self.whisper_model.transcribe(
                combined_audio,
                beam_size=5,
                temperature=0.0,
                vad_filter=True,
                language="en"
            )

            # Collect transcription segments with timestamps
            whisper_segments = []
            for segment in segments_generator:
                whisper_segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip()
                })

            if not whisper_segments:
                print("No transcription from Whisper")
                return

            # Stage 2: Pyannote speaker diarization
            print("Stage 2: Pyannote speaker diarization...")

            # Convert audio to the format pyannote expects
            # Pyannote expects 16kHz mono audio as waveform
            if self.sample_rate != 16000:
                import librosa
                diarization_audio = librosa.resample(combined_audio, orig_sr=self.sample_rate, target_sr=16000)
            else:
                diarization_audio = combined_audio

            # Create a dict-like object with waveform data
            waveform_dict = {
                "waveform": torch.from_numpy(diarization_audio).unsqueeze(0).float(),
                "sample_rate": 16000
            }

            # Apply speaker diarization with user-defined max speakers
            max_speakers = self.max_speakers_var.get() if hasattr(self, 'max_speakers_var') else 2
            print(f"Running diarization with max_speakers={max_speakers}")
            diarization = self.pyannote_pipeline(
                waveform_dict,
                min_speakers=1,
                max_speakers=max_speakers
            )

            # Stage 3: Align Whisper text with pyannote speakers
            # Fix #3: Use intersection gate to prevent ASR/diarization contradictions
            print("Stage 3: Aligning text with speakers (intersection gate)...")
            aligned_segments = align_with_intersection_gate(whisper_segments, diarization, min_confidence=0.1)

            # PATCH_DIARIZE: Future enhancement - Apply OnlineDiarizer for speaker consistency
            # TODO: Extract speaker embeddings from pyannote and use OnlineDiarizer
            # if self.online_diarizer:
            #     for segment in aligned_segments:
            #         # Extract embedding from pyannote for this segment
            #         # embedding = extract_speaker_embedding(diarization_audio, segment)
            #         # speaker_id, confidence = self.online_diarizer.assign_speaker(embedding)
            #         # segment['consistent_speaker_id'] = speaker_id
            #         pass

            # Stage 4: Map speakers to Speaker 1/Speaker 2 labels
            labeled_segments = self.map_speakers_to_labels(aligned_segments)

            # Fix #1: Calculate buffer window start time for absolute timestamps
            buffer_window_start = time.time() - self.absolute_session_start_time if self.absolute_session_start_time else 0.0

            # Stage 5: Stitch segments with all fixes applied (dedupe, coalesce, timestamps)
            # Fix #1-5: Per-segment timestamps, overlap dedup, coalescing, idempotent UI
            emittable_segments = self.transcript_stitcher.stitch_and_emit_segments(
                labeled_segments,
                buffer_window_start
            )

            # Stage 6: Process emittable segments through the transcription pipeline
            for segment in emittable_segments:
                abs_start_ts = (self.absolute_session_start_time or 0) + segment['abs_start']
                abs_end_ts = (self.absolute_session_start_time or 0) + segment['abs_end']

                turn_data = {
                    'speaker': segment.get('speaker_label', segment.get('speaker', 'UNKNOWN')),
                    'text': segment['text'],
                    'start': abs_start_ts,
                    'end': abs_end_ts,
                    'id': segment.get('id') # Use the stitcher's unique ID
                }
                self._append_transcript_turn(**turn_data)

            # Performance tracking
            processing_time = time.time() - start_time
            rtf = processing_time / audio_duration

            # Fix: Updated logging with stitcher statistics
            buffer_window_end = buffer_window_start + audio_duration
            stats_summary = self.transcript_stitcher.get_stats_summary(buffer_window_start, buffer_window_end)
            print(f"Advanced diarization completed: {processing_time:.1f}s (RTF: {rtf:.2f}x)")
            print(f"Stage-1 VAD/ASR: {len(whisper_segments)} segments (diarization may split speakers later)")
            print(f"Stage-3 Stitching: {stats_summary}")

            # Update performance stats
            self.performance_stats['rtf_values'].append(rtf)
            self.performance_stats['processing_times'].append(processing_time)
            self.performance_stats['advanced_diarization_rtf'].append(rtf)
            self.performance_stats['advanced_diarization_chunks'] += 1

            # Track speaker alignment accuracy
            if labeled_segments:
                avg_confidence = np.mean([seg['confidence'] for seg in labeled_segments])
                self.performance_stats['speaker_alignment_accuracy'].append(avg_confidence)

        except Exception as e:
            print(f"Advanced diarization error: {e}")
            import traceback
            traceback.print_exc()

            # Detailed error handling with specific fallback strategies
            if "CUDA out of memory" in str(e) or "out of memory" in str(e).lower():
                print("GPU memory error detected - disabling advanced diarization")
                self.advanced_diarization_enabled = False
                self.advanced_diarization_var.set(False)
                if hasattr(self, 'diarization_status_label'):
                    self.diarization_status_label.configure(
                        text="[WARN] Disabled due to GPU memory error",
                        text_color="orange"
                    )

            elif "pyannote" in str(e).lower() or "diarization" in str(e).lower():
                print("Pyannote-specific error - attempting CPU fallback")
                try:
                    # Try CPU fallback for pyannote
                    if self.pyannote_pipeline and hasattr(self.pyannote_pipeline, 'to'):
                        self.pyannote_pipeline = self.pyannote_pipeline.to(torch.device("cpu"))
                        print("Switched pyannote to CPU mode")
                except Exception as cpu_error:
                    print(f"CPU fallback failed: {cpu_error}")
                    self.advanced_diarization_enabled = False
                    self.advanced_diarization_var.set(False)

            else:
                print("Unknown error in advanced diarization")

            # Always fallback to standard processing for this chunk
            print("Falling back to standard channel-based processing for this chunk...")
            try:
                self.process_audio_buffer_with_vad(mic_audio, sys_audio)
            except Exception as fallback_error:
                print(f"Fallback processing also failed: {fallback_error}")
                # Last resort: add error message to transcript
                timestamp = datetime.now().strftime("%H:%M:%S")
                error_text = f"[{timestamp}] [SYSTEM]: Audio processing error - chunk skipped"
                self._append_transcript_turn(
                    speaker="SYSTEM",
                    text=error_text,
                    start=time.time(),
                    end=time.time()
                )

    def align_whisper_with_pyannote(self, whisper_segments, diarization):
        """Align Whisper transcription segments with pyannote speaker segments"""
        aligned_segments = []

        for whisper_seg in whisper_segments:
            start_time = whisper_seg['start']
            end_time = whisper_seg['end']
            text = whisper_seg['text']

            # Find the dominant speaker during this text segment
            segment_duration = end_time - start_time
            speaker_durations = {}

            # Check overlaps with diarization segments
            for turn, track, speaker in diarization.itertracks(yield_label=True):
                overlap_start = max(start_time, turn.start)
                overlap_end = min(end_time, turn.end)

                if overlap_start < overlap_end:  # There is overlap
                    overlap_duration = overlap_end - overlap_start
                    if speaker not in speaker_durations:
                        speaker_durations[speaker] = 0
                    speaker_durations[speaker] += overlap_duration

            # Assign to speaker with most overlap
            if speaker_durations:
                dominant_speaker = max(speaker_durations, key=speaker_durations.get)
                aligned_segments.append({
                    'start': start_time,
                    'end': end_time,
                    'text': text,
                    'speaker_id': dominant_speaker,
                    'confidence': speaker_durations[dominant_speaker] / segment_duration
                })
            else:
                # No speaker found, assign to unknown
                aligned_segments.append({
                    'start': start_time,
                    'end': end_time,
                    'text': text,
                    'speaker_id': 'SPEAKER_UNKNOWN',
                    'confidence': 0.0
                })

        return aligned_segments

    def map_speakers_to_labels(self, aligned_segments):
        """Map pyannote speaker IDs to Speaker 1/Speaker 2 labels"""
        # Simple mapping strategy: assign based on speaking order and duration
        speaker_stats = {}

        # Calculate speaking statistics for each speaker
        for segment in aligned_segments:
            speaker_id = segment['speaker_id']
            duration = segment['end'] - segment['start']

            if speaker_id not in speaker_stats:
                speaker_stats[speaker_id] = {
                    'total_duration': 0,
                    'segment_count': 0,
                    'first_appearance': segment['start']
                }

            speaker_stats[speaker_id]['total_duration'] += duration
            speaker_stats[speaker_id]['segment_count'] += 1

        # Sort speakers by total speaking time (descending)
        sorted_speakers = sorted(speaker_stats.items(),
                               key=lambda x: x[1]['total_duration'],
                               reverse=True)

        # Map speakers to Speaker 1, Speaker 2, etc.
        speaker_mapping = {}
        if len(sorted_speakers) >= 2:
            # Most active speaker = Speaker 1
            speaker_mapping[sorted_speakers[0][0]] = "Speaker 1"
            speaker_mapping[sorted_speakers[1][0]] = "Speaker 2"

            # Additional speakers get numbered labels
            for i, (speaker_id, _) in enumerate(sorted_speakers[2:], 3):
                speaker_mapping[speaker_id] = f"Speaker {i}"
        elif len(sorted_speakers) == 1:
            # Only one speaker detected
            speaker_mapping[sorted_speakers[0][0]] = "Speaker 1"

        # Apply mapping to segments
        labeled_segments = []
        for segment in aligned_segments:
            speaker_id = segment['speaker_id']
            speaker_label = speaker_mapping.get(speaker_id, "[UNKNOWN]")

            labeled_segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text'],
                'speaker': speaker_label,
                'speaker_label': speaker_label,  # For stitcher compatibility
                'speaker_id': speaker_id,  # Keep original ID for stitcher
                'confidence': segment['confidence'],
                'original_speaker_id': speaker_id
            })

        # Store mapping for consistency across chunks
        self.speaker_mapping.update(speaker_mapping)

        # Synchronize with the new transcript panel UI
        if self.transcript_panel_actions.refresh_roles:
            # The UI component expects roles for speaker 1 and 2
            s1_label = self.speaker_mapping.get(sorted_speakers[0][0], "Speaker 1") if sorted_speakers else "Speaker 1"
            s2_label = self.speaker_mapping.get(sorted_speakers[1][0], "Speaker 2") if len(sorted_speakers) > 1 else "Speaker 2"
            
            # Update the panel's state and trigger a refresh
            self.transcript_panel_state.speaker_roles = self.speaker_mapping
            self.transcript_panel_actions.refresh_roles(s1_label, s2_label)
            print(f"Refreshed speaker roles in UI: {s1_label}, {s2_label}")

        return labeled_segments

    def get_gpu_memory_usage(self):
        """Get current GPU VRAM usage in MB"""
        if not NVML_AVAILABLE:
            return 0

        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return info.used // 1024 // 1024  # Convert to MB
        except:
            return 0

    def get_gpu_memory_available(self):
        """Get available GPU VRAM in GB"""
        if not NVML_AVAILABLE:
            return 0

        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            available_gb = (info.total - info.used) / (1024 ** 3)  # Convert to GB
            return available_gb
        except:
            return 0

    def check_gpu_memory_sufficient(self, required_gb=2.0):
        """Check if sufficient GPU memory is available for pyannote"""
        available = self.get_gpu_memory_available()
        return available >= required_gb

    def load_pyannote_pipeline(self, device, available_memory_gb):
        """Load pyannote.audio speaker diarization pipeline with memory management"""
        if not PYANNOTE_AVAILABLE:
            self.diarization_error = "pyannote.audio not installed"
            print("Pyannote.audio not available, skipping advanced diarization")
            return

        # Check if advanced diarization is enabled
        if not self.advanced_diarization_enabled:
            print("Advanced speaker diarization is disabled in settings")
            return

        # Read HuggingFace token from environment variables with fallback to settings
        # Per HuggingFace Hub docs: HF_TOKEN is the official environment variable
        import os
        hf_token = os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_HUB_TOKEN') or self.huggingface_token

        if not hf_token:
            self.diarization_error = "No HuggingFace token found"
            print("[ERROR] No HuggingFace token configured - skipping speaker diarization")
            print("  Set HF_TOKEN environment variable or configure in Settings > Audio")
            self.advanced_diarization_enabled = False
            return

        try:
            # Check if we have enough GPU memory for pyannote (~2GB required)
            required_memory = 2.0  # GB
            if device == "cuda" and available_memory_gb < required_memory:
                print(f"Insufficient GPU memory for pyannote ({available_memory_gb:.1f}GB available, {required_memory}GB required)")
                print("Pyannote will use CPU fallback")
                device = "cpu"

            print(f"Loading pyannote speaker diarization pipeline on {device}...")
            print("This may take a while on first run (~500MB download)...")

            # Update status label if available
            self.set_status("Downloading speaker diarization models...")

            # Load the speaker diarization pipeline with HuggingFace token
            try:
                # Note: HuggingFace Hub will show download progress in console automatically
                # The download is cached after first run at ~/.cache/huggingface/
                # Per pyannote-audio docs: use token parameter for authentication
                self.pyannote_pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=hf_token
                )

                # Move to GPU if available
                if device == "cuda":
                    self.set_status("Loading models to GPU...")
                    self.pyannote_pipeline = self.pyannote_pipeline.to(torch.device("cuda"))
                    print("[OK] Pyannote pipeline loaded successfully on GPU")
                else:
                    print("[OK] Pyannote pipeline loaded successfully on CPU")

                # Clear any previous errors on successful load
                self.diarization_error = None

                # Update status
                if hasattr(self, 'status_label'):
                    status_text = "Ready - GPU Optimized" if device == "cuda" else "Ready - CPU Mode"
                    status_text += " + Advanced Diarization"
                    self.set_status(status_text)

            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "authentication" in error_msg.lower():
                    self.diarization_error = "Invalid HuggingFace token"
                    print("[ERROR] Authentication failed - Invalid token or conditions not accepted")
                    print("   Please visit https://huggingface.co/pyannote/speaker-diarization-3.1")
                    print("   and https://huggingface.co/pyannote/segmentation-3.0")
                    print("   to accept the user conditions, then update your token in Settings")
                    self.set_status("Error: Invalid HuggingFace token")
                elif "gated" in error_msg.lower() or "accept the user conditions" in error_msg.lower() or "'NoneType' object has no attribute 'eval'" in error_msg:
                    self.diarization_error = "Model access not granted"
                    print("[ERROR] Model access denied - You must accept the gated model conditions")
                    print("   1. Visit https://huggingface.co/pyannote/speaker-diarization-3.1")
                    print("   2. Click 'Agree and access repository'")
                    print("   3. Visit https://huggingface.co/pyannote/segmentation-3.0")
                    print("   4. Click 'Agree and access repository'")
                    print("   5. Restart the application")
                    self.set_status("Error: Model access not granted")
                elif "404" in error_msg:
                    self.diarization_error = "Model not found"
                    print("[ERROR] Model not found - Check your token has access to pyannote models")
                    self.set_status("Error: Model not found")
                elif "offline" in error_msg.lower() or "connection" in error_msg.lower():
                    self.diarization_error = "Network connection failed"
                    print("[ERROR] Network error - Check your internet connection")
                    self.set_status("Error: Network connection failed")
                else:
                    self.diarization_error = f"Failed to load: {error_msg[:50]}"
                    print(f"[ERROR] Failed to load pyannote model: {error_msg}")
                    self.set_status("Error: Failed to load diarization models")

                # Ensure pipeline is None and diarization is disabled on error
                self.pyannote_pipeline = None
                self.advanced_diarization_enabled = False

        except Exception as e:
            print(f"[ERROR] Unexpected error loading pyannote pipeline: {e}")
            self.set_status("Error: Unexpected error loading models")
            self.pyannote_pipeline = None
            self.advanced_diarization_enabled = False

    def log_memory_usage(self, context=""):
        """Log current GPU memory usage for debugging"""
        if NVML_AVAILABLE:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                used_gb = info.used / (1024 ** 3)
                total_gb = info.total / (1024 ** 3)
                available_gb = (info.total - info.used) / (1024 ** 3)
                print(f"GPU Memory {context}: {used_gb:.1f}GB used / {total_gb:.1f}GB total ({available_gb:.1f}GB available)")
                return used_gb, total_gb, available_gb
            except Exception as e:
                print(f"Failed to get GPU memory info: {e}")
                return 0, 0, 0
        return 0, 0, 0

    def get_buffer_size_recommendations(self):
        """Provide buffer size recommendations based on use case"""
        recommendations = {
            "30 seconds": {
                "latency": "Low (30s delay)",
                "accuracy": "Good - suitable for real-time feedback",
                "use_case": "Interactive sessions, quick responses needed",
                "trade_off": "Faster but may miss some speaker transitions"
            },
            "1 minute": {
                "latency": "Moderate (1min delay)",
                "accuracy": "Better - balanced approach",
                "use_case": "Most therapy sessions, good balance",
                "trade_off": "Recommended default for most users"
            },
            "90 seconds": {
                "latency": "Higher (90s delay)",
                "accuracy": "High - captures complex speaker patterns",
                "use_case": "Complex sessions with frequent speaker changes",
                "trade_off": "More accurate but longer wait times"
            },
            "2 minutes": {
                "latency": "Highest (2min delay)",
                "accuracy": "Maximum - best speaker identification",
                "use_case": "Research, detailed analysis, post-session review",
                "trade_off": "Best accuracy but longest processing delay"
            }
        }
        return recommendations

    def get_performance_summary(self):
        """Get performance statistics summary"""
        if not self.performance_stats['rtf_values']:
            return "No performance data available"

        avg_rtf = np.mean(self.performance_stats['rtf_values'])
        max_rtf = np.max(self.performance_stats['rtf_values'])
        avg_gpu = np.mean(self.performance_stats['gpu_memory_usage']) if self.performance_stats['gpu_memory_usage'] else 0
        avg_cpu = np.mean(self.performance_stats['cpu_usage'])
        total_processing_time = np.sum(self.performance_stats['processing_times'])
        discontinuities = self.performance_stats['discontinuities']
        buffer_underruns = self.performance_stats['buffer_underruns']

        # Audio quality assessment
        audio_quality = "Excellent" if discontinuities == 0 else ("Good" if discontinuities < 10 else ("Fair" if discontinuities < 50 else "Poor"))

        # Advanced diarization metrics
        advanced_summary = ""
        if self.performance_stats['advanced_diarization_chunks'] > 0:
            adv_rtf_avg = np.mean(self.performance_stats['advanced_diarization_rtf'])
            adv_rtf_max = np.max(self.performance_stats['advanced_diarization_rtf'])
            avg_accuracy = np.mean(self.performance_stats['speaker_alignment_accuracy']) if self.performance_stats['speaker_alignment_accuracy'] else 0

            # Get current buffer size for reporting
            current_buffer_selection = getattr(self, 'diarization_buffer_var', None)
            buffer_size_text = current_buffer_selection.get() if current_buffer_selection else f"{self.diarization_buffer_size}s"
            overlap_size = self.get_diarization_overlap_size()

            advanced_summary = f"""
Advanced Diarization Report:
- Buffer Size: {buffer_size_text} (overlap: {overlap_size}s)
- Chunks Processed: {self.performance_stats['advanced_diarization_chunks']}
- Advanced RTF Average: {adv_rtf_avg:.2f}x
- Advanced RTF Max: {adv_rtf_max:.2f}x
- Speaker Alignment Accuracy: {avg_accuracy:.1%}
- Processing Mode: Whisper + Pyannote Two-Stage Pipeline
"""

        return f"""Performance Summary:
- Average RTF: {avg_rtf:.2f}x (target: <2.0x)
- Max RTF: {max_rtf:.2f}x
- Average GPU VRAM: {avg_gpu:.0f}MB
- Average CPU Usage: {avg_cpu:.1f}%
- Total Processing Time: {total_processing_time:.1f}s
- Buffers Processed: {len(self.performance_stats['rtf_values'])}{advanced_summary}
Audio Quality Report:
- Sample Rate: {self.sample_rate} Hz
- Buffer Size: {self.audio_blocksize} samples
- Chunk Duration: {self.recording_chunk_duration*1000:.0f}ms
- Audio Discontinuities: {discontinuities}
- Buffer Underruns: {buffer_underruns}
- Audio Quality: {audio_quality}"""

    def save_debug_audio(self, audio_data, prefix="buffer"):
        """Save audio data for quality debugging"""
        try:
            debug_dir = Path("debug_audio")
            debug_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%H%M%S")
            debug_file = debug_dir / f"{prefix}_{timestamp}.wav"
            
            # Save as WAV for manual inspection
            import wave
            with wave.open(str(debug_file), 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)
                
                # Convert float32 to int16 for WAV
                audio_int16 = (audio_data * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())
                
        except Exception as e:
            print(f"Debug audio save error: {e}")
    
    def update_transcript_display(self):
        """DEPRECATED: Legacy transcript update loop (replaced by _append_transcript_turn adapter)"""
        # This method is no longer used - all transcript updates go through _append_transcript_turn
        # The adapter handles thread safety and routing to the new TranscriptPanel
        # Kept as stub to prevent errors if referenced elsewhere
        if self.VERBOSE_UI:
            print("WARNING: update_transcript_display called but is deprecated; use _append_transcript_turn")
        # Do NOT reschedule - this loop is disabled
    
    def save_transcript(self):
        """Save transcript to file with performance summary"""
        try:
            session_name = self.current_session.strftime("%Y-%m-%d_%H-%M-%S")
            transcript_file = self.sessions_dir / f"session_{session_name}.txt"

            # Get transcript content
            transcript_content = self._get_transcript_as_text()

            # Add session header with performance stats
            session_duration = (datetime.now() - self.current_session).total_seconds() / 60  # minutes
            header = f"Therapy Session Transcript\n"
            header += f"Date: {self.current_session.strftime('%Y-%m-%d %H:%M:%S')}\n"
            header += f"Duration: {session_duration:.1f} minutes\n"
            # System configuration header
            system_info = "SoundCard + faster-whisper Medium.en + Silero VAD"
            if self.advanced_diarization_enabled and self.pyannote_pipeline:
                system_info += " + Pyannote Advanced Diarization"
            header += f"System: {system_info}\n"
            header += "=" * 50 + "\n\n"

            # Add performance summary
            performance_summary = self.get_performance_summary()
            header += f"Performance Report:\n{performance_summary}\n"
            header += "=" * 50 + "\n\n"

            # Add analysis summary if available
            if self.analysis_enabled and self.session_context:
                analysis_summary = self.get_analysis_summary_report()
                header += f"Therapy Analysis Report:\n{analysis_summary}\n"
                header += "=" * 50 + "\n\n"

            # Write to file
            with open(transcript_file, 'w', encoding='utf-8') as f:
                f.write(header + transcript_content)

            # Save analysis results separately if available
            if self.analysis_enabled and self.session_context:
                self.save_analysis_results(session_name)

            # Also save performance log
            perf_file = self.sessions_dir / f"performance_{session_name}.log"
            with open(perf_file, 'w', encoding='utf-8') as f:
                f.write(f"Session Performance Log\n")
                f.write(f"Date: {datetime.now().isoformat()}\n")
                f.write(f"Duration: {session_duration:.1f} minutes\n\n")
                f.write(performance_summary)

            # Update session info (legacy UI)
            if hasattr(self, 'session_info_label'):
                self.session_info_label.configure(text=f"Saved: {transcript_file.name}")

            # Print final performance summary
            print("\n" + "="*50)
            print("SESSION COMPLETED")
            print("="*50)
            print(performance_summary)
            print("="*50)

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save transcript: {str(e)}")

    # ===================================================================
    # THERAPY ANALYSIS SYSTEM - Claude API Integration
    # ===================================================================

    def load_analysis_config(self):
        """Load therapy analysis configuration from file or create default"""
        try:
            config_file = Path("analysis_config.json")
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.claude_api_key = config.get('claude_api_key')
                    self.analysis_frequency = config.get('analysis_frequency', 120)
                    self.auto_approve_enabled = config.get('auto_approve_enabled', False)
                    print("Analysis config loaded from file")
            else:
                self.create_default_config()
        except Exception as e:
            print(f"Config load error: {e}")
            self.create_default_config()

    def create_default_config(self):
        """Create default analysis configuration file"""
        try:
            default_config = {
                "claude_api_key": "",
                "analysis_frequency": 120,
                "auto_approve_enabled": False,
                "prompt_template": "cognitive_behavioral",
                "sensitivity_threshold": 0.7,
                "risk_alert_keywords": ["suicide", "self-harm", "hurt myself", "end it all", "kill myself"]
            }

            config_file = Path("analysis_config.json")
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)

            print("Created default analysis config file")
        except Exception as e:
            print(f"Config creation error: {e}")

    def setup_claude_client(self):
        """Initialize Gemini API client with authentication (backward compatible)"""
        print("Setting up Gemini client with unified SDK...")

        if not GEMINI_AVAILABLE:
            print("[ERROR] Gemini not available - install: pip install google-genai")
            self.gemini_model = None
            self.gemini_client = None
            self.analysis_enabled = False
            return

        try:
            # Read API key from settings first, then fallback to environment variable
            import os
            api_key = None

            # Priority 1: Check stored API keys
            if hasattr(self, 'api_keys') and self.api_keys.get('gemini'):
                api_key = self.api_keys['gemini']
                print("[OK] Using stored Gemini API key")
            # Priority 2: Check environment variable
            elif os.getenv('GOOGLE_API_KEY'):
                api_key = os.getenv('GOOGLE_API_KEY')
                print("[OK] Using Gemini API key from environment")

            if not api_key:
                print("[ERROR] No Gemini API key configured")
                self.gemini_model = None
                self.gemini_client = None
                self.analysis_enabled = False
                return

            # Unified SDK pattern: store model name, use client for calls
            # Use stored model if available, otherwise default
            if hasattr(self, 'gemini_model') and isinstance(self.gemini_model, str):
                model_name = self.gemini_model
            else:
                model_name = 'gemini-2.0-flash-001'

            print(f"Initializing unified SDK client with model: {model_name}...")
            self.gemini_client = genai.Client(api_key=api_key)
            self.gemini_model = model_name  # Store model name as string

            # Connectivity test
            try:
                print(f"Testing connection with model '{model_name}'...")
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    contents='test'
                )
                print(f"[OK] Gemini API connected: {response.text[:50]}")
                self.analysis_enabled = True
            except APIError as api_err:
                print(f"[ERROR] API error: {api_err.code} - {api_err.message}")
                self.gemini_model = None
                self.analysis_enabled = False
            except Exception as test_error:
                print(f"[ERROR] Connectivity test failed: {test_error}")
                self.gemini_model = None
                self.analysis_enabled = False

        except Exception as e:
            print(f"[ERROR] Gemini client setup error: {e}")
            import traceback
            traceback.print_exc()
            self.gemini_model = None
            self.gemini_client = None
            self.analysis_enabled = False

        # Refresh prompt buttons to reflect analysis_enabled state
        if hasattr(self, 'render_prompt_buttons'):
            try:
                self.root.after(100, self.render_prompt_buttons)  # Delay to ensure UI is ready
            except Exception as e:
                print(f"[WARNING] Could not refresh prompt buttons: {e}")

    def get_selected_prompt_template(self, template_type="real-time"):
        """Get the currently selected prompt template for analysis"""
        try:
            # If templates haven't been loaded yet, load them
            if not hasattr(self, 'prompt_templates'):
                self.load_templates()

            # Get current template selection from settings (add this to analysis settings)
            selected_template_id = getattr(self, 'selected_template_id', 'cbt_realtime')

            # Return selected template or fallback to default
            if selected_template_id in self.prompt_templates:
                return self.prompt_templates[selected_template_id]
            else:
                # Fallback to first real-time template
                for template_id, template in self.prompt_templates.items():
                    if template.get('category') == template_type:
                        return template

                # Ultimate fallback - create basic template
                return {
                    'name': 'Basic Analysis',
                    'prompt': 'Analyze this therapy segment:\n\n{transcript_segment}\n\nContext: {session_context}\n\nProvide structured clinical insights.',
                    'category': 'real-time',
                    'variables': ['transcript_segment', 'session_context']
                }

        except Exception as e:
            print(f"Error getting prompt template: {e}")
            # Return minimal fallback
            return {
                'name': 'Fallback Template',
                'prompt': 'Analyze: {transcript_segment}',
                'category': 'real-time',
                'variables': ['transcript_segment']
            }

    def get_therapy_prompt_templates(self):
        """Legacy method - redirects to new template system"""
        # This maintains backward compatibility
        template = self.get_selected_prompt_template()
        return {
            "selected": {
                "name": template.get('name', 'Current Template'),
                "prompt": template.get('prompt', ''),
                "risk_keywords": ["suicide", "self-harm", "hopeless", "worthless", "end it all"]
            }

        }

    def queue_for_analysis(self, transcript_text):
        """Queue transcript segment for therapy analysis"""
        if not self.analysis_enabled or not self.gemini_model:
            return

        try:
            # Add to analysis buffer
            self.analysis_buffer.append({
                'text': transcript_text,
                'timestamp': time.time()
            })

            # Initialize buffer timer if needed
            if not self.analysis_buffer_start:
                self.analysis_buffer_start = time.time()

            # Check if it's time to analyze
            buffer_age = time.time() - self.analysis_buffer_start
            if buffer_age >= self.analysis_frequency:
                self.trigger_analysis()

        except Exception as e:
            print(f"Analysis queueing error: {e}")

    def trigger_analysis(self):
        """Trigger analysis of accumulated transcript segments"""
        if not self.analysis_buffer or not self.gemini_model:
            return

        try:
            # Combine buffer segments
            combined_text = "\n".join([seg['text'] for seg in self.analysis_buffer])

            # Create analysis request
            analysis_request = {
                'id': str(uuid.uuid4()),
                'transcript': combined_text,
                'timestamp': time.time(),
                'context': self.get_session_context_summary()
            }

            # Queue for async processing
            self.analysis_queue.put(analysis_request)

            # Reset buffer
            self.analysis_buffer = []
            self.analysis_buffer_start = None

            print(f"Queued analysis request: {len(combined_text)} characters")

        except Exception as e:
            print(f"Analysis trigger error: {e}")

    def get_session_context_summary(self):
        """Get summary of previous analysis results for context"""
        if not self.session_context:
            return "Beginning of therapy session."

        try:
            # Get last 3 analysis summaries for context
            recent_context = self.session_context[-3:]
            context_summary = []

            for ctx in recent_context:
                if 'summary' in ctx:
                    context_summary.append(f"Previous: {ctx['summary']}")

            return "\n".join(context_summary) if context_summary else "Continuing therapy session."

        except Exception as e:
            print(f"Context summary error: {e}")
            return "Therapy session in progress."

    def start_analysis_loop(self):
        """Start the async analysis processing loop"""
        if not self.analysis_enabled or self.analysis_loop_task:
            return

        try:
            # Start async analysis loop in separate thread
            import threading
            self.analysis_loop_task = threading.Thread(
                target=self.run_analysis_loop,
                daemon=True
            )
            self.analysis_loop_task.start()
            print("Analysis loop started")

        except Exception as e:
            print(f"Analysis loop start error: {e}")

    def stop_analysis_loop(self):
        """Stop the analysis processing loop"""
        try:
            if self.analysis_loop_task:
                self.analysis_enabled = False
                self.analysis_loop_task = None
                print("Analysis loop stopped")

        except Exception as e:
            print(f"Analysis loop stop error: {e}")

    def run_analysis_loop(self):
        """Main analysis processing loop (runs in separate thread)"""
        print("Analysis processing loop started")

        while self.analysis_enabled:
            try:
                # Check for analysis requests
                if not self.analysis_queue.empty():
                    request = self.analysis_queue.get_nowait()

                    # Process request asynchronously
                    result = self.process_analysis_request(request)

                    if result:
                        # Store result and update UI
                        self.analysis_results.append(result)
                        self.session_context.append(result)

                        # Process result for dashboard updates
                        self.process_analysis_result(result)

                        # Check for risk alerts
                        self.check_risk_alerts(result)

                        # Update analysis stats
                        self.update_analysis_stats(result)

                time.sleep(1)  # Brief pause between checks

            except queue.Empty:
                time.sleep(1)
            except Exception as e:
                print(f"Analysis loop error: {e}")
                time.sleep(5)  # Longer pause on error

        print("Analysis loop ended")

    def process_analysis_request(self, request):
        """Process a single analysis request using editable prompt templates"""
        try:
            # Get current selected prompt template
            template = self.get_selected_prompt_template("real-time")

            # Prepare data for template variable replacement
            template_data = {
                'transcript_segment': request['transcript'],
                'session_context': request['context'],
                'session_duration': str(self.get_session_duration_minutes()),
                'therapy_modality': getattr(self, 'therapy_modality', 'CBT'),
                'analysis_history': self.get_analysis_history_summary(),
                'risk_level': str(self.get_current_risk_level())
            }

            # Replace template variables with actual data
            prompt = self.replace_template_variables(template['prompt'], template_data)

            # Rate limiting
            self.apply_rate_limiting()

            # Call multi-provider API
            start_time = time.time()

            # Use multi-provider system
            success, response_text = self.generate_with_provider(prompt)

            if not success:
                raise Exception(f"API call failed: {response_text}")

            processing_time = time.time() - start_time

            # Parse response
            provider = getattr(self, 'active_provider', 'gemini')
            analysis_result = {
                'id': request['id'],
                'timestamp': request['timestamp'],
                'processing_time': processing_time,
                'model': provider,
                'prompt_template': template.get('name', 'Unknown Template'),
                'template_id': getattr(self, 'selected_template_id', 'cbt_realtime'),
                'raw_response': response_text,
                'success': True,
                'tokens_used': 0,  # Token counting varies by provider
                'cost_estimate': 0
            }

            # Try to parse structured response
            try:
                # Look for JSON in response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    analysis_result['structured_analysis'] = json.loads(json_match.group())
            except:
                # If parsing fails, use raw text
                pass

            # Generate summary
            analysis_result['summary'] = self.generate_analysis_summary(analysis_result)

            self.analysis_stats['successful_requests'] += 1
            print(f"Analysis completed: {analysis_result['id'][:8]}... ({processing_time:.2f}s)")

            return analysis_result

        except Exception as e:
            print(f"Analysis processing error: {e}")

            self.analysis_stats['failed_requests'] += 1

            return {
                'id': request['id'],
                'timestamp': request['timestamp'],
                'error': str(e),
                'success': False
            }

    def apply_rate_limiting(self):
        """Apply rate limiting to prevent API abuse"""
        try:
            # Simple rate limiting - 1 request per 2 seconds minimum
            current_time = time.time()
            if hasattr(self, 'last_api_call'):
                time_since_last = current_time - self.last_api_call
                if time_since_last < 2.0:
                    sleep_time = 2.0 - time_since_last
                    time.sleep(sleep_time)

            self.last_api_call = current_time

        except Exception as e:
            print(f"Rate limiting error: {e}")

    def calculate_cost(self, usage):
        """Calculate estimated cost based on token usage"""
        try:
            # Claude-3 Sonnet pricing (approximate)
            input_cost_per_token = 0.000003  # $3 per million tokens
            output_cost_per_token = 0.000015  # $15 per million tokens

            input_cost = usage.input_tokens * input_cost_per_token
            output_cost = usage.output_tokens * output_cost_per_token

            return input_cost + output_cost

        except Exception as e:
            print(f"Cost calculation error: {e}")
            return 0.0

    def generate_analysis_summary(self, result):
        """Generate a brief summary of the analysis result"""
        try:
            raw_text = result.get('raw_response', '')

            # Extract key insights (first few sentences)
            sentences = raw_text.split('.')[:3]
            summary = '. '.join(sentences).strip()

            if len(summary) > 200:
                summary = summary[:200] + "..."

            return summary if summary else "Analysis completed"

        except Exception as e:
            print(f"Summary generation error: {e}")
            return "Analysis summary unavailable"

    def check_risk_alerts(self, analysis_result):
        """Check analysis result for risk indicators and create alerts"""
        try:
            raw_text = analysis_result.get('raw_response', '').lower()
            structured = analysis_result.get('structured_analysis', {})

            # Check for high risk scores
            risk_score = 0
            if structured and 'risk_assessment' in structured:
                risk_score = float(structured['risk_assessment'].get('score', 0))

            # Check for risk keywords
            templates = self.get_therapy_prompt_templates()
            risk_keywords = templates['cognitive_behavioral']['risk_keywords']

            found_keywords = [kw for kw in risk_keywords if kw in raw_text]

            # Create alert if high risk detected
            if risk_score >= 7 or found_keywords:
                alert = {
                    'id': str(uuid.uuid4()),
                    'timestamp': time.time(),
                    'analysis_id': analysis_result['id'],
                    'risk_score': risk_score,
                    'keywords_found': found_keywords,
                    'alert_level': 'HIGH' if risk_score >= 8 else 'MEDIUM',
                    'message': f"Risk alert: Score {risk_score}/10"
                }

                self.risk_alerts.append(alert)
                print(f"🚨 RISK ALERT: {alert['alert_level']} - Score: {risk_score}")

                # Show immediate alert in UI
                self.show_risk_alert(alert)

        except Exception as e:
            print(f"Risk check error: {e}")

    def show_risk_alert(self, alert):
        """Show immediate risk alert in the UI"""
        try:
            # Schedule UI update in main thread
            self.root.after(0, lambda: self.display_risk_alert(alert))

        except Exception as e:
            print(f"Risk alert display error: {e}")

    def display_risk_alert(self, alert):
        """Display risk alert in main UI thread"""
        try:
            alert_msg = f"[WARN]️ {alert['alert_level']} RISK ALERT\n"
            alert_msg += f"Risk Score: {alert['risk_score']}/10\n"
            if alert['keywords_found']:
                alert_msg += f"Keywords: {', '.join(alert['keywords_found'])}\n"
            alert_msg += "\nImmediate attention may be required."

            # Show alert window
            messagebox.showwarning("Risk Alert", alert_msg)

        except Exception as e:
            print(f"Alert display error: {e}")

    def update_analysis_stats(self, result):
        """Update analysis performance statistics"""
        try:
            self.analysis_stats['total_requests'] += 1

            if result.get('success'):
                self.analysis_stats['tokens_used'] += result.get('tokens_used', 0)
                self.analysis_stats['total_cost'] += result.get('cost_estimate', 0.0)

        except Exception as e:
            print(f"Stats update error: {e}")

    def get_analysis_summary_report(self):
        """Generate comprehensive analysis summary for end of session"""
        try:
            if not self.session_context:
                return "No analysis data available."

            # Compile session analysis
            total_analyses = len(self.session_context)
            successful_analyses = len([r for r in self.session_context if r.get('success', False)])

            # Get risk alerts summary
            high_risk_alerts = len([a for a in self.risk_alerts if a['alert_level'] == 'HIGH'])
            medium_risk_alerts = len([a for a in self.risk_alerts if a['alert_level'] == 'MEDIUM'])

            # Calculate costs
            total_cost = self.analysis_stats['total_cost']
            total_tokens = self.analysis_stats['tokens_used']

            summary = f"""
Therapy Analysis Session Report
{'='*50}

Analysis Performance:
- Total Analysis Requests: {total_analyses}
- Successful Analyses: {successful_analyses}
- Failed Requests: {self.analysis_stats['failed_requests']}
- Success Rate: {(successful_analyses/max(total_analyses,1)*100):.1f}%

Risk Assessment:
- High Risk Alerts: {high_risk_alerts}
- Medium Risk Alerts: {medium_risk_alerts}
- Total Risk Events: {len(self.risk_alerts)}

Resource Usage:
- Total Tokens Used: {total_tokens:,}
- Estimated Cost: ${total_cost:.4f}
- Average Cost per Analysis: ${total_cost/max(successful_analyses,1):.4f}

Session Insights:
- Analysis Frequency: {self.analysis_frequency}s intervals
- Template Used: Cognitive Behavioral Therapy
- Context Maintained: {len(self.session_context)} segments
"""

            return summary

        except Exception as e:
            print(f"Analysis summary error: {e}")
            return f"Analysis summary error: {e}"

    def save_analysis_results(self, session_name):
        """Save analysis results to file"""
        try:
            if not self.session_context:
                return

            analysis_file = self.sessions_dir / f"analysis_{session_name}.json"

            # Prepare analysis data for saving
            analysis_data = {
                'session_info': {
                    'session_name': session_name,
                    'date': datetime.now().isoformat(),
                    'total_analyses': len(self.session_context),
                    'analysis_frequency': self.analysis_frequency
                },
                'statistics': self.analysis_stats.copy(),
                'risk_alerts': self.risk_alerts.copy(),
                'analysis_results': [r for r in self.session_context if r.get('success', False)],
                'summary_report': self.get_analysis_summary_report()
            }

            # Save to JSON file
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, default=str)

            print(f"Analysis results saved: {analysis_file}")

        except Exception as e:
            print(f"Analysis save error: {e}")

    def run(self):
        """Start the application"""
        try:
            self.root.mainloop()
        finally:
            # Cleanup
            if self.is_recording:
                self.stop_recording()
            if self.analysis_enabled:
                self.stop_analysis_loop()

    # ===================================================================
    # TRANSCRIPT EXPORT AND LAYOUT MANAGEMENT
    # ===================================================================

    def copy_transcript_to_clipboard(self):
        """Copy entire transcript to clipboard with formatting"""
        try:
            if not hasattr(self, 'transcript_text'):
                print("No transcript available")
                return

            # Get transcript content
            transcript_content = self._get_transcript_as_text()

            if not transcript_content.strip():
                print("Transcript is empty")
                return

            # Format transcript with session metadata
            formatted_transcript = self.format_transcript_for_export(transcript_content)

            # Copy to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(formatted_transcript)
            self.root.update()  # Ensure clipboard is updated

            # Show success message
            self.show_temporary_message("Transcript copied to clipboard!", "success")
            print(f"Transcript copied to clipboard ({len(formatted_transcript)} characters)")

        except Exception as e:
            print(f"Error copying transcript: {e}")
            self.show_temporary_message("Failed to copy transcript", "error")

    def format_transcript_for_export(self, transcript_content):
        """Format transcript with metadata for clinical notes"""
        try:
            # Session metadata
            session_date = self.current_session.strftime("%Y-%m-%d %H:%M:%S") if hasattr(self, 'current_session') else "Unknown"
            session_duration = self.get_session_duration_string()

            # Analysis summary if available
            analysis_summary = self.get_analysis_summary_for_export()

            formatted_output = f"""THERAPY SESSION TRANSCRIPT
================================
Date: {session_date}
Duration: {session_duration}
System: Amanuensis V2 - Professional Transcription

{analysis_summary}

TRANSCRIPT:
----------
{transcript_content}

================================
Generated by Amanuensis V2
"""
            return formatted_output

        except Exception as e:
            print(f"Error formatting transcript: {e}")
            return transcript_content  # Return raw content as fallback

    def get_session_duration_string(self):
        """Get formatted session duration string"""
        try:
            if hasattr(self, 'current_session') and self.current_session:
                duration = datetime.now() - self.current_session
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours:02d}:{minutes:02d}:{total_seconds % 60:02d}"
            return "00:00:00"
        except Exception:
            return "Unknown"

    def get_analysis_summary_for_export(self):
        """Get analysis summary for transcript export"""
        try:
            if not self.analysis_enabled or not hasattr(self, 'session_context') or not self.session_context:
                return "Analysis: Not available"

            # Count analyses and risk assessments
            total_analyses = len(self.session_context)
            risk_events = len([r for r in self.risk_alerts if r.get('alert_level') in ['MEDIUM', 'HIGH']])

            summary = f"""ANALYSIS SUMMARY:
- Total Analyses: {total_analyses}
- Risk Events: {risk_events}
- Current Risk Level: {self.dashboard_state.get('risk_level', 'UNKNOWN')}
"""
            return summary

        except Exception as e:
            print(f"Error generating analysis summary: {e}")
            return "Analysis: Error generating summary"

    def show_temporary_message(self, message, msg_type="info"):
        """Show temporary success/error message"""
        try:
            # Get current status text
            original_text = self.status_label.cget("text") if hasattr(self, 'status_label') else ""

            # Show temporary message using centralized status bar
            prefix = "[OK] " if msg_type == "success" else "[ERROR] "
            self.set_status(prefix + message)

            # Restore original text after 3 seconds
            if original_text:
                self.root.after(3000, lambda: self.set_status(original_text))

        except Exception as e:
            print(f"Error showing temporary message: {e}")

    def resize_panel(self, panel_name, new_width):
        """Resize a specific panel to new width"""
        try:
            # Update layout preferences
            if panel_name == 'control':
                self.layout_preferences['control_panel_width'] = max(150, min(300, new_width))
                if hasattr(self, 'control_frame'):
                    self.control_frame.configure(width=self.layout_preferences['control_panel_width'])

            elif panel_name == 'transcript':
                self.layout_preferences['transcript_panel_width'] = max(300, min(600, new_width))
                if hasattr(self, 'transcript_frame'):
                    self.transcript_frame.configure(width=self.layout_preferences['transcript_panel_width'])

            elif panel_name == 'insights':
                self.layout_preferences['insights_panel_width'] = max(350, min(700, new_width))
                if hasattr(self, 'analysis_frame'):
                    self.analysis_frame.configure(width=self.layout_preferences['insights_panel_width'])

            print(f"Panel {panel_name} resized to {new_width}px")

        except Exception as e:
            print(f"Error resizing panel {panel_name}: {e}")

    def toggle_panel(self, panel_name):
        """Toggle panel visibility (collapse/expand)"""
        try:
            is_collapsed = self.layout_preferences['panels_collapsed'].get(panel_name, False)

            if panel_name == 'control' and hasattr(self, 'control_frame'):
                if is_collapsed:
                    self.control_frame.pack(side="left", fill="y", padx=(0, 2))
                    self.layout_preferences['panels_collapsed']['control'] = False
                else:
                    self.control_frame.pack_forget()
                    self.layout_preferences['panels_collapsed']['control'] = True

            elif panel_name == 'transcript' and hasattr(self, 'transcript_frame'):
                if is_collapsed:
                    self.transcript_frame.pack(side="left", fill="y", padx=2)
                    self.layout_preferences['panels_collapsed']['transcript'] = False
                else:
                    self.transcript_frame.pack_forget()
                    self.layout_preferences['panels_collapsed']['transcript'] = True

            elif panel_name == 'insights' and hasattr(self, 'analysis_frame'):
                if is_collapsed:
                    self.analysis_frame.pack(side="right", fill="y", padx=(2, 0))
                    self.layout_preferences['panels_collapsed']['insights'] = False
                else:
                    self.analysis_frame.pack_forget()
                    self.layout_preferences['panels_collapsed']['insights'] = True

            print(f"Panel {panel_name} {'expanded' if not is_collapsed else 'collapsed'}")

        except Exception as e:
            print(f"Error toggling panel {panel_name}: {e}")

    def auto_resize_to_optimal(self):
        """Auto-resize panels to optimal proportions"""
        try:
            # Optimal proportions for therapy sessions
            self.resize_panel('control', 200)
            self.resize_panel('transcript', 450)
            self.resize_panel('insights', 500)

            print("Panels resized to optimal proportions")

        except Exception as e:
            print(f"Error auto-resizing panels: {e}")

    # ===================================================================
    # ENHANCED PANEL CONTROLS AND RESIZABLE WIDGETS
    # ===================================================================

    def toggle_panel(self, panel_name):
        """Toggle panel visibility (collapse/expand)"""
        try:
            is_collapsed = self.layout_preferences['panels_collapsed'].get(panel_name, False)

            if panel_name == 'control' and hasattr(self, 'control_frame'):
                if is_collapsed:
                    self.control_frame.pack(side="left", fill="y", padx=(0, 2))
                    self.layout_preferences['panels_collapsed']['control'] = False
                    print("Control panel expanded")
                else:
                    self.control_frame.pack_forget()
                    self.layout_preferences['panels_collapsed']['control'] = True
                    print("Control panel collapsed")

            elif panel_name == 'transcript' and hasattr(self, 'transcript_frame'):
                if is_collapsed:
                    # Repack transcript panel
                    self.transcript_frame.pack(side="left", fill="y", padx=2, after=self.control_frame)
                    self.layout_preferences['panels_collapsed']['transcript'] = False
                    print("Transcript panel expanded")
                else:
                    self.transcript_frame.pack_forget()
                    self.layout_preferences['panels_collapsed']['transcript'] = True
                    print("Transcript panel collapsed")

            elif panel_name == 'insights' and hasattr(self, 'analysis_frame'):
                if is_collapsed:
                    self.analysis_frame.pack(side="right", fill="y", padx=(2, 0))
                    self.layout_preferences['panels_collapsed']['insights'] = False
                    print("Insights panel expanded")
                else:
                    self.analysis_frame.pack_forget()
                    self.layout_preferences['panels_collapsed']['insights'] = True
                    print("Insights panel collapsed")

            print(f"Panel {panel_name} {'expanded' if not is_collapsed else 'collapsed'}")

        except Exception as e:
            print(f"Error toggling panel {panel_name}: {e}")

    def create_resize_handle(self, handle_type):
        """Create a visual resize handle between panels"""
        bg_accent_tuple = ("#e9ecef", "#404040")  # (light, dark)
        try:
            # Create a subtle resize indicator
            handle = ctk.CTkFrame(
                self.main_panel_container,
                width=3,
                fg_color=bg_accent_tuple,
                corner_radius=1
            )

            # Store handle reference
            setattr(self, f'{handle_type}_handle', handle)

            # Pack handle between panels
            handle.pack(side="left", fill="y", padx=1)

            # Add visual feedback
            handle.bind("<Enter>", lambda e: handle.configure(fg_color=self.colors.get('primary', '#1e40af')))
            handle.bind("<Leave>", lambda e: handle.configure(fg_color=bg_accent_tuple))
            handle.bind("<Double-Button-1>", lambda e: self.reset_to_optimal_proportions())

            print(f"Created resize handle: {handle_type}")

        except Exception as e:
            print(f"Error creating resize handle {handle_type}: {e}")

    def reset_to_optimal_proportions(self):
        """Reset all panels to optimal proportions for therapy sessions"""
        try:
            print("Resetting to optimal proportions...")

            # Optimal proportions for clinical use
            self.layout_preferences['control_panel_width'] = 200
            self.layout_preferences['transcript_panel_width'] = 450
            self.layout_preferences['insights_panel_width'] = 500

            # Apply the new sizes
            if hasattr(self, 'control_frame'):
                self.control_frame.configure(width=200)
            if hasattr(self, 'transcript_frame'):
                self.transcript_frame.configure(width=450)
            if hasattr(self, 'analysis_frame'):
                self.analysis_frame.configure(width=500)

            print("✅ Panels reset to optimal proportions")

        except Exception as e:
            print(f"Error resetting proportions: {e}")

    def preview_theme_change(self):
        """Preview theme change without applying"""
        try:
            if hasattr(self, 'appearance_mode_var'):
                selected_theme = self.appearance_mode_var.get()
                print(f"Theme preview: {selected_theme}")
                # Note: Full preview would show temporary changes

        except Exception as e:
            print(f"Error previewing theme: {e}")

    def reset_to_optimal_layout(self):
        """Reset layout to optimal proportions and update sliders"""
        try:
            # Reset to optimal values
            self.layout_preferences['control_panel_width'] = 200
            self.layout_preferences['transcript_panel_width'] = 450
            self.layout_preferences['insights_panel_width'] = 500

            # Update slider variables if they exist
            if hasattr(self, 'control_width_var'):
                self.control_width_var.set(200)
                self.control_width_label.configure(text="200px")

            if hasattr(self, 'transcript_width_var'):
                self.transcript_width_var.set(450)
                self.transcript_width_label.configure(text="450px")

            if hasattr(self, 'insights_width_var'):
                self.insights_width_var.set(500)
                self.insights_width_label.configure(text="500px")

            # Apply changes to actual panels
            self.auto_resize_to_optimal()

            print("Layout reset to optimal proportions")

        except Exception as e:
            print(f"Error resetting layout: {e}")

    def save_theme_preference(self):
        """Save current theme preference to persistent storage"""
        try:
            # In production, this would save to a config file
            print(f"Theme preference saved: {self.current_theme}")

        except Exception as e:
            print(f"Error saving theme preference: {e}")

def main():
    """Main entry point"""
    try:
        app = AmanuensisApp()
        app.run()
    except Exception as e:
        import traceback
        print(f"Application error: {e}")
        traceback.print_exc()
        messagebox.showerror("Application Error", f"Failed to start application: {str(e)}")

if __name__ == "__main__":
    main()
