#!/usr/bin/env python3
"""
Centralized Logging Configuration for Amanuensis
Provides robust debugging and monitoring capabilities
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path


class AmanuensisLogger:
    """Centralized logger for the Amanuensis application"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AmanuensisLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._setup_logging()
            AmanuensisLogger._initialized = True

    def _setup_logging(self):
        """Setup logging configuration"""
        # Create logs directory
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        # Generate log file names with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.main_log_file = self.log_dir / f"amanuensis_{timestamp}.log"
        self.error_log_file = self.log_dir / f"amanuensis_errors_{timestamp}.log"
        self.audio_log_file = self.log_dir / f"amanuensis_audio_{timestamp}.log"

        # Configure root logger
        self.root_logger = logging.getLogger()
        self.root_logger.setLevel(logging.DEBUG)

        # Clear any existing handlers
        self.root_logger.handlers.clear()

        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)-20s | %(levelname)-8s | %(funcName)-15s:%(lineno)-4d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )

        # Console handler - INFO and above
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        self.root_logger.addHandler(console_handler)

        # Main log file handler - DEBUG and above
        file_handler = logging.FileHandler(self.main_log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        self.root_logger.addHandler(file_handler)

        # Error log file handler - WARNING and above
        error_handler = logging.FileHandler(self.error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(detailed_formatter)
        self.root_logger.addHandler(error_handler)

        # Audio-specific log file handler
        audio_handler = logging.FileHandler(self.audio_log_file, encoding='utf-8')
        audio_handler.setLevel(logging.DEBUG)
        audio_handler.setFormatter(detailed_formatter)

        # Add rotating file handler to prevent huge log files
        rotating_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / "amanuensis_rotating.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        rotating_handler.setLevel(logging.DEBUG)
        rotating_handler.setFormatter(detailed_formatter)
        self.root_logger.addHandler(rotating_handler)

        # Setup specific loggers
        self._setup_component_loggers(audio_handler)

        # Log startup message
        startup_logger = logging.getLogger(__name__)
        startup_logger.info("="*80)
        startup_logger.info("AMANUENSIS LOGGING SYSTEM INITIALIZED")
        startup_logger.info(f"Main log file: {self.main_log_file}")
        startup_logger.info(f"Error log file: {self.error_log_file}")
        startup_logger.info(f"Audio log file: {self.audio_log_file}")
        startup_logger.info("="*80)

    def _setup_component_loggers(self, audio_handler):
        """Setup specific component loggers"""
        # Audio manager logger
        audio_logger = logging.getLogger('audio_manager')
        audio_logger.addHandler(audio_handler)
        audio_logger.setLevel(logging.DEBUG)

        # Session recorder logger
        session_logger = logging.getLogger('session_recorder')
        session_logger.setLevel(logging.DEBUG)

        # Whisper manager logger
        whisper_logger = logging.getLogger('whisper_manager')
        whisper_logger.setLevel(logging.DEBUG)

        # Main application logger
        main_logger = logging.getLogger('amanuensis_main')
        main_logger.setLevel(logging.DEBUG)

        # Insights dashboard logger
        insights_logger = logging.getLogger('insights_dashboard')
        insights_logger.setLevel(logging.DEBUG)

    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger for a specific component"""
        return logging.getLogger(name)

    def log_system_info(self):
        """Log system information for debugging"""
        logger = self.get_logger('system_info')

        logger.info("SYSTEM INFORMATION:")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Script path: {sys.argv[0] if sys.argv else 'Unknown'}")

        # Log environment variables
        important_env_vars = ['PATH', 'PYTHONPATH', 'HOME', 'USER', 'USERNAME']
        for var in important_env_vars:
            value = os.environ.get(var, 'Not set')
            logger.info(f"ENV {var}: {value}")

    def log_exception(self, logger_name: str, exception: Exception, context: str = ""):
        """Log an exception with full traceback"""
        logger = self.get_logger(logger_name)
        import traceback

        logger.error(f"EXCEPTION in {context}: {type(exception).__name__}: {str(exception)}")
        logger.error("FULL TRACEBACK:")
        for line in traceback.format_exc().splitlines():
            logger.error(f"  {line}")

    def log_performance(self, logger_name: str, operation: str, duration: float, details: dict = None):
        """Log performance metrics"""
        logger = self.get_logger(logger_name)

        logger.info(f"PERFORMANCE: {operation} took {duration:.3f}s")
        if details:
            for key, value in details.items():
                logger.info(f"  {key}: {value}")

    def log_audio_levels(self, mic_level: float, system_level: float, timestamp: str = None):
        """Log audio levels for debugging"""
        logger = self.get_logger('audio_levels')

        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        logger.debug(f"AUDIO_LEVELS [{timestamp}] Mic: {mic_level:.1f} | System: {system_level:.1f}")

    def cleanup_old_logs(self, days_to_keep: int = 7):
        """Clean up old log files"""
        logger = self.get_logger('log_cleanup')

        try:
            cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)

            for log_file in self.log_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_date:
                    log_file.unlink()
                    logger.info(f"Deleted old log file: {log_file}")

        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")


def get_logger(name: str) -> logging.Logger:
    """Convenience function to get a logger"""
    AmanuensisLogger()  # Ensure logging is initialized
    return logging.getLogger(name)


def log_function_call(logger_name: str):
    """Decorator to log function calls"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name)
            logger.debug(f"CALL: {func.__name__}({len(args)} args, {len(kwargs)} kwargs)")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"RETURN: {func.__name__} -> {type(result).__name__}")
                return result
            except Exception as e:
                logger.error(f"EXCEPTION in {func.__name__}: {type(e).__name__}: {str(e)}")
                raise

        return wrapper
    return decorator


# Initialize logging system when module is imported
_logger_instance = AmanuensisLogger()


if __name__ == "__main__":
    # Test logging system
    logger = get_logger('test')

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    # Test exception logging
    try:
        raise ValueError("Test exception")
    except Exception as e:
        _logger_instance.log_exception('test', e, "testing exception logging")

    # Test performance logging
    import time
    start = time.time()
    time.sleep(0.1)
    _logger_instance.log_performance('test', 'sleep operation', time.time() - start, {'sleep_duration': 0.1})

    print(f"Logs created in: {_logger_instance.log_dir.absolute()}")