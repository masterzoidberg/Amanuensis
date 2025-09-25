#!/usr/bin/env python3
"""
Transcription Health Monitor
Comprehensive error handling and health monitoring for the transcription system
"""

import time
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Error categories for classification"""
    MODEL_LOAD = "model_load"
    MODEL_INFERENCE = "model_inference"
    AUDIO_FORMAT = "audio_format"
    AUDIO_DEVICE = "audio_device"
    STORAGE = "storage"
    NETWORK = "network"
    SYSTEM_RESOURCE = "system_resource"
    CONFIGURATION = "configuration"

@dataclass
class HealthMetric:
    """Health metric data"""
    name: str
    value: float
    status: HealthStatus
    threshold_warning: float = None
    threshold_error: float = None
    unit: str = ""
    description: str = ""
    last_updated: float = None

@dataclass
class ErrorReport:
    """Error report structure"""
    category: ErrorCategory
    severity: HealthStatus
    message: str
    timestamp: float
    context: Dict = None
    correlation_id: str = None
    count: int = 1

class TranscriptionHealthMonitor:
    """Comprehensive health monitoring for transcription system"""
    
    def __init__(self):
        from logger_config import get_logger
        self.logger = get_logger('health_monitor')
        
        # Health metrics
        self.metrics = {}
        self.metrics_lock = threading.Lock()
        
        # Error tracking
        self.errors = []
        self.error_counts = {}
        self.errors_lock = threading.Lock()
        
        # Health callbacks
        self.health_callbacks = []
        
        # Monitoring state
        self.monitoring = False
        self.monitor_thread = None
        self.monitor_interval = 10  # seconds
        
        # Health thresholds
        self.thresholds = {
            'model_load_time': {'warning': 30, 'error': 60},  # seconds
            'inference_latency': {'warning': 5, 'error': 15},  # seconds
            'queue_size': {'warning': 10, 'error': 20},  # items
            'error_rate': {'warning': 0.1, 'error': 0.3},  # ratio
            'memory_usage': {'warning': 0.8, 'error': 0.95},  # ratio
            'disk_usage': {'warning': 0.8, 'error': 0.95},  # ratio
        }
        
        # Initialize metrics
        self._initialize_metrics()
        
        self.logger.info("Transcription Health Monitor initialized")

    def _initialize_metrics(self):
        """Initialize health metrics"""
        metrics = [
            HealthMetric("model_loaded", 0, HealthStatus.ERROR, description="Model loading status (0=not loaded, 1=loaded)"),
            HealthMetric("inference_latency", 0, HealthStatus.HEALTHY, 5, 15, "s", "Average inference latency"),
            HealthMetric("queue_size", 0, HealthStatus.HEALTHY, 10, 20, "items", "Processing queue size"),
            HealthMetric("error_rate", 0, HealthStatus.HEALTHY, 0.1, 0.3, "ratio", "Error rate over last hour"),
            HealthMetric("total_segments", 0, HealthStatus.HEALTHY, description="Total segments processed"),
            HealthMetric("memory_usage", 0, HealthStatus.HEALTHY, 0.8, 0.95, "ratio", "System memory usage"),
            HealthMetric("disk_usage", 0, HealthStatus.HEALTHY, 0.8, 0.95, "ratio", "Disk usage"),
            HealthMetric("audio_level", 0, HealthStatus.HEALTHY, description="Current audio input level"),
        ]
        
        with self.metrics_lock:
            for metric in metrics:
                metric.last_updated = time.time()
                self.metrics[metric.name] = metric

    def start_monitoring(self):
        """Start health monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Health monitoring started")

    def stop_monitoring(self):
        """Stop health monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("Health monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                self._update_system_metrics()
                self._check_health_thresholds()
                self._notify_health_callbacks()
                time.sleep(self.monitor_interval)
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)

    def _update_system_metrics(self):
        """Update system-level metrics"""
        try:
            import psutil
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.update_metric("memory_usage", memory.percent / 100)
            
            # Disk usage
            disk = psutil.disk_usage('.')
            self.update_metric("disk_usage", disk.percent / 100)
            
        except ImportError:
            # psutil not available, skip system metrics
            pass
        except Exception as e:
            self.logger.debug(f"Error updating system metrics: {e}")

    def _check_health_thresholds(self):
        """Check metrics against thresholds and update status"""
        with self.metrics_lock:
            for metric in self.metrics.values():
                if metric.threshold_error and metric.value >= metric.threshold_error:
                    metric.status = HealthStatus.ERROR
                elif metric.threshold_warning and metric.value >= metric.threshold_warning:
                    metric.status = HealthStatus.WARNING
                else:
                    metric.status = HealthStatus.HEALTHY

    def _notify_health_callbacks(self):
        """Notify registered health callbacks"""
        try:
            health_summary = self.get_health_summary()
            for callback in self.health_callbacks:
                try:
                    callback(health_summary)
                except Exception as e:
                    self.logger.error(f"Error in health callback: {e}")
        except Exception as e:
            self.logger.error(f"Error notifying health callbacks: {e}")

    def update_metric(self, name: str, value: float):
        """Update a health metric"""
        with self.metrics_lock:
            if name in self.metrics:
                self.metrics[name].value = value
                self.metrics[name].last_updated = time.time()
            else:
                self.logger.warning(f"Unknown metric: {name}")

    def report_error(self, category: ErrorCategory, severity: HealthStatus, 
                    message: str, context: Dict = None, correlation_id: str = None):
        """Report an error"""
        error = ErrorReport(
            category=category,
            severity=severity,
            message=message,
            timestamp=time.time(),
            context=context or {},
            correlation_id=correlation_id
        )
        
        with self.errors_lock:
            # Check for duplicate errors
            error_key = f"{category.value}:{message}"
            if error_key in self.error_counts:
                self.error_counts[error_key] += 1
                # Update existing error count
                for existing_error in self.errors:
                    if (existing_error.category == category and 
                        existing_error.message == message):
                        existing_error.count = self.error_counts[error_key]
                        existing_error.timestamp = time.time()
                        break
            else:
                self.error_counts[error_key] = 1
                self.errors.append(error)
            
            # Keep only recent errors (last 1000)
            if len(self.errors) > 1000:
                self.errors = self.errors[-500:]
        
        # Update error rate metric
        self._update_error_rate()
        
        # Log the error
        log_level = {
            HealthStatus.WARNING: logging.WARNING,
            HealthStatus.ERROR: logging.ERROR,
            HealthStatus.CRITICAL: logging.CRITICAL
        }.get(severity, logging.ERROR)
        
        self.logger.log(log_level, f"[{category.value}] {message}")

    def _update_error_rate(self):
        """Update error rate metric"""
        try:
            current_time = time.time()
            hour_ago = current_time - 3600
            
            with self.errors_lock:
                recent_errors = [e for e in self.errors if e.timestamp > hour_ago]
                total_operations = max(1, self.metrics.get('total_segments', {}).value or 1)
                error_rate = len(recent_errors) / total_operations
                
            self.update_metric("error_rate", error_rate)
        except Exception as e:
            self.logger.debug(f"Error updating error rate: {e}")

    def get_health_summary(self) -> Dict:
        """Get overall health summary"""
        with self.metrics_lock:
            metrics_data = {name: asdict(metric) for name, metric in self.metrics.items()}
        
        with self.errors_lock:
            recent_errors = [asdict(e) for e in self.errors[-10:]]  # Last 10 errors
        
        # Determine overall status
        overall_status = HealthStatus.HEALTHY
        for metric in self.metrics.values():
            if metric.status == HealthStatus.CRITICAL:
                overall_status = HealthStatus.CRITICAL
                break
            elif metric.status == HealthStatus.ERROR and overall_status != HealthStatus.CRITICAL:
                overall_status = HealthStatus.ERROR
            elif metric.status == HealthStatus.WARNING and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.WARNING
        
        return {
            'overall_status': overall_status.value,
            'timestamp': time.time(),
            'metrics': metrics_data,
            'recent_errors': recent_errors,
            'error_counts': dict(self.error_counts),
            'monitoring': self.monitoring
        }

    def get_health_status(self) -> HealthStatus:
        """Get overall health status"""
        return HealthStatus(self.get_health_summary()['overall_status'])

    def add_health_callback(self, callback: Callable[[Dict], None]):
        """Add health status callback"""
        self.health_callbacks.append(callback)

    def clear_errors(self):
        """Clear error history"""
        with self.errors_lock:
            self.errors.clear()
            self.error_counts.clear()
        self.logger.info("Error history cleared")

    def get_error_summary(self, category: ErrorCategory = None) -> Dict:
        """Get error summary, optionally filtered by category"""
        with self.errors_lock:
            errors = self.errors
            if category:
                errors = [e for e in errors if e.category == category]
            
            summary = {
                'total_errors': len(errors),
                'by_category': {},
                'by_severity': {},
                'recent_errors': errors[-5:] if errors else []
            }
            
            for error in errors:
                # Count by category
                cat = error.category.value
                summary['by_category'][cat] = summary['by_category'].get(cat, 0) + error.count
                
                # Count by severity
                sev = error.severity.value
                summary['by_severity'][sev] = summary['by_severity'].get(sev, 0) + error.count
            
            return summary

    def create_error_context(self, **kwargs) -> Dict:
        """Create error context dictionary"""
        context = {
            'timestamp': time.time(),
            'thread': threading.current_thread().name,
        }
        context.update(kwargs)
        return context

# Global health monitor instance
_health_monitor = None

def get_health_monitor() -> TranscriptionHealthMonitor:
    """Get global health monitor instance"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = TranscriptionHealthMonitor()
    return _health_monitor

def report_model_load_error(message: str, **context):
    """Convenience function to report model loading errors"""
    monitor = get_health_monitor()
    monitor.report_error(
        ErrorCategory.MODEL_LOAD,
        HealthStatus.ERROR,
        message,
        monitor.create_error_context(**context)
    )

def report_inference_error(message: str, **context):
    """Convenience function to report inference errors"""
    monitor = get_health_monitor()
    monitor.report_error(
        ErrorCategory.MODEL_INFERENCE,
        HealthStatus.ERROR,
        message,
        monitor.create_error_context(**context)
    )

def report_audio_error(message: str, **context):
    """Convenience function to report audio errors"""
    monitor = get_health_monitor()
    monitor.report_error(
        ErrorCategory.AUDIO_FORMAT,
        HealthStatus.ERROR,
        message,
        monitor.create_error_context(**context)
    )

def report_storage_error(message: str, **context):
    """Convenience function to report storage errors"""
    monitor = get_health_monitor()
    monitor.report_error(
        ErrorCategory.STORAGE,
        HealthStatus.WARNING,
        message,
        monitor.create_error_context(**context)
    )

def update_model_status(loaded: bool):
    """Update model loading status"""
    monitor = get_health_monitor()
    monitor.update_metric("model_loaded", 1.0 if loaded else 0.0)

def update_inference_latency(latency: float):
    """Update inference latency metric"""
    monitor = get_health_monitor()
    monitor.update_metric("inference_latency", latency)

def update_queue_size(size: int):
    """Update processing queue size"""
    monitor = get_health_monitor()
    monitor.update_metric("queue_size", size)

def increment_segments_processed():
    """Increment total segments processed"""
    monitor = get_health_monitor()
    current = monitor.metrics.get("total_segments", {}).value or 0
    monitor.update_metric("total_segments", current + 1)

def test_health_monitor():
    """Test the health monitoring system"""
    print("Testing Transcription Health Monitor")
    print("=" * 50)
    
    # Get monitor instance
    monitor = get_health_monitor()
    
    # Start monitoring
    monitor.start_monitoring()
    
    # Test metric updates
    update_model_status(True)
    update_inference_latency(2.5)
    update_queue_size(5)
    
    # Test error reporting
    report_model_load_error("Test model load error", model="test-model")
    report_inference_error("Test inference error", audio_length=3.0)
    report_audio_error("Test audio format error", format="unknown")
    
    # Get health summary
    health = monitor.get_health_summary()
    print(f"Overall Status: {health['overall_status']}")
    print(f"Metrics: {len(health['metrics'])}")
    print(f"Recent Errors: {len(health['recent_errors'])}")
    
    # Test error summary
    error_summary = monitor.get_error_summary()
    print(f"Total Errors: {error_summary['total_errors']}")
    print(f"By Category: {error_summary['by_category']}")
    
    # Stop monitoring
    monitor.stop_monitoring()
    
    print("✅ Health monitor test completed")

if __name__ == "__main__":
    test_health_monitor()
