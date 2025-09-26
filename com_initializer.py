#!/usr/bin/env python3
"""
Windows COM Initialization Helper for WASAPI Audio
Handles proper COM apartment threading for audio device access
"""

import sys
import threading
import atexit
from contextlib import contextmanager
from typing import Dict, Optional

# Windows COM constants
COINIT_APARTMENTTHREADED = 0x2
COINIT_MULTITHREADED = 0x0
COINIT_DISABLE_OLE1DDE = 0x4
COINIT_SPEED_OVER_MEMORY = 0x8

# Thread-local COM state tracking
_thread_local = threading.local()
_global_com_state: Dict[int, bool] = {}
_com_lock = threading.Lock()

def _get_com_library():
    """Import COM library (Windows only)"""
    try:
        if sys.platform == "win32":
            import pythoncom
            return pythoncom
        else:
            return None
    except ImportError:
        return None

def is_com_initialized() -> bool:
    """Check if COM is initialized in current thread"""
    thread_id = threading.current_thread().ident
    with _com_lock:
        return _global_com_state.get(thread_id, False)

def initialize_com_for_audio() -> bool:
    """Initialize COM for WASAPI audio access in current thread"""
    if sys.platform != "win32":
        return True  # Non-Windows systems don't need COM

    pythoncom = _get_com_library()
    if not pythoncom:
        return False

    thread_id = threading.current_thread().ident

    # Check if already initialized for this thread
    if is_com_initialized():
        return True

    try:
        # Initialize COM with apartment threading (required for WASAPI)
        # Use COINIT_APARTMENTTHREADED for compatibility with most audio APIs
        pythoncom.CoInitializeEx(COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE)

        # Mark as initialized for this thread
        with _com_lock:
            _global_com_state[thread_id] = True

        return True

    except Exception as e:
        # COM may already be initialized with different threading model
        # This is common and usually not an error
        try:
            # Try to use existing COM initialization
            pythoncom.CoInitialize()
            with _com_lock:
                _global_com_state[thread_id] = True
            return True
        except:
            # If both fail, COM initialization is problematic
            return False

def uninitialize_com() -> None:
    """Uninitialize COM for current thread"""
    if sys.platform != "win32":
        return

    pythoncom = _get_com_library()
    if not pythoncom:
        return

    thread_id = threading.current_thread().ident

    if is_com_initialized():
        try:
            pythoncom.CoUninitialize()
        except:
            pass  # Ignore uninit errors
        finally:
            with _com_lock:
                _global_com_state.pop(thread_id, None)

@contextmanager
def com_context():
    """Context manager for COM initialization/cleanup"""
    initialized = initialize_com_for_audio()
    try:
        yield initialized
    finally:
        if initialized:
            uninitialize_com()

def com_audio_safe(func):
    """Decorator to ensure COM is initialized for audio functions"""
    def wrapper(*args, **kwargs):
        if not initialize_com_for_audio():
            raise RuntimeError("Failed to initialize COM for audio operations")
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Check if this is a COM error and provide helpful message
            error_str = str(e)
            if "0x800401f0" in error_str or "CoInitialize" in error_str:
                raise RuntimeError(
                    f"COM initialization error: {error_str}. "
                    "Try running as administrator or check Windows audio service."
                ) from e
            else:
                raise
    return wrapper

# Cleanup COM on module exit
@atexit.register
def cleanup_com():
    """Clean up COM state on exit"""
    with _com_lock:
        for thread_id in list(_global_com_state.keys()):
            _global_com_state.pop(thread_id, None)

if __name__ == "__main__":
    # Test COM initialization
    print("Testing COM initialization...")

    if sys.platform == "win32":
        print(f"Platform: Windows")
        print(f"COM initialized: {is_com_initialized()}")

        success = initialize_com_for_audio()
        print(f"COM init result: {success}")
        print(f"COM initialized after init: {is_com_initialized()}")

        uninitialize_com()
        print(f"COM initialized after uninit: {is_com_initialized()}")
    else:
        print(f"Platform: {sys.platform} (COM not needed)")