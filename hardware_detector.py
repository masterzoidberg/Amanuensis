#!/usr/bin/env python3
"""
Hardware Detection and Whisper Model Recommendation System
"""

import psutil
import platform
import shutil
import os
import subprocess
from typing import Dict, List, Tuple, Optional

class HardwareDetector:
    """Detects system hardware capabilities and recommends optimal Whisper models"""

    def __init__(self):
        self.system_info = self._detect_system()
        self.model_specs = {
            'tiny': {
                'size_mb': 39,
                'description': 'Fast, basic accuracy',
                'speed_multiplier': 32,
                'memory_mb': 390,
                'use_case': 'Quick testing or very low-resource systems'
            },
            'base': {
                'size_mb': 74,
                'description': 'Good balance',
                'speed_multiplier': 16,
                'memory_mb': 500,
                'use_case': 'General purpose, balanced performance'
            },
            'small': {
                'size_mb': 244,
                'description': 'Recommended for therapy',
                'speed_multiplier': 6,
                'memory_mb': 1000,
                'use_case': 'Optimal for therapy sessions - good accuracy and speed'
            },
            'medium': {
                'size_mb': 769,
                'description': 'High accuracy',
                'speed_multiplier': 2,
                'memory_mb': 2000,
                'use_case': 'High accuracy needs, slower processing'
            },
            'large': {
                'size_mb': 1550,
                'description': 'Best accuracy, slower',
                'speed_multiplier': 1,
                'memory_mb': 4000,
                'use_case': 'Maximum accuracy, requires powerful hardware'
            }
        }

    def _detect_system(self) -> Dict:
        """Detect system hardware and capabilities"""
        # Get platform info first to avoid circular dependency
        platform_name = platform.system()

        info = {
            'cpu_cores': psutil.cpu_count(logical=False),
            'cpu_threads': psutil.cpu_count(logical=True),
            'ram_gb': round(psutil.virtual_memory().total / (1024**3)),
            'available_ram_gb': round(psutil.virtual_memory().available / (1024**3)),
            'disk_free_gb': round(shutil.disk_usage('.').free / (1024**3)),
            'platform': platform_name,
            'architecture': platform.architecture()[0],
            'gpu_info': self._detect_gpu(platform_name),
            'cuda_available': self._check_cuda(),
            'metal_available': self._check_metal(platform_name)
        }
        return info

    def _detect_gpu(self, platform_info: str = None) -> Dict:
        """Detect GPU hardware"""
        gpu_info = {
            'has_gpu': False,
            'gpu_name': 'Not detected',
            'gpu_memory_gb': 0,
            'gpu_type': 'none'
        }

        try:
            # Try NVIDIA first
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split(', ')
                    if len(parts) >= 2:
                        gpu_info['has_gpu'] = True
                        gpu_info['gpu_name'] = parts[0]
                        gpu_info['gpu_memory_gb'] = int(parts[1]) // 1024
                        gpu_info['gpu_type'] = 'nvidia'
                        break
        except:
            pass

        # Try AMD/Intel detection if NVIDIA not found
        if not gpu_info['has_gpu']:
            try:
                # This is a simplified detection - could be expanded
                if platform_info == 'Darwin':  # macOS
                    # Check for Apple Silicon
                    result = subprocess.run(['system_profiler', 'SPHardwareDataType'],
                                          capture_output=True, text=True, timeout=5)
                    if 'Apple' in result.stdout and ('M1' in result.stdout or 'M2' in result.stdout or 'M3' in result.stdout):
                        gpu_info['has_gpu'] = True
                        gpu_info['gpu_name'] = 'Apple Silicon'
                        gpu_info['gpu_memory_gb'] = 8  # Shared memory
                        gpu_info['gpu_type'] = 'apple'
            except:
                pass

        return gpu_info

    def _check_cuda(self) -> bool:
        """Check if CUDA is available"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            try:
                result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True, timeout=5)
                return result.returncode == 0
            except:
                return False

    def _check_metal(self, platform_info: str = None) -> bool:
        """Check if Metal Performance Shaders (macOS) is available"""
        if platform_info != 'Darwin':
            return False
        try:
            import torch
            return hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
        except ImportError:
            return platform_info == 'Darwin'

    def get_model_recommendation(self) -> str:
        """Get recommended Whisper model based on hardware"""
        ram_gb = self.system_info['ram_gb']
        gpu_info = self.system_info['gpu_info']

        # High-end system
        if ram_gb >= 16 and (gpu_info['has_gpu'] and gpu_info['gpu_memory_gb'] >= 8):
            return 'medium'

        # Good system with GPU
        elif ram_gb >= 8 and gpu_info['has_gpu']:
            return 'small'

        # Decent system without GPU or limited GPU
        elif ram_gb >= 8:
            return 'small'

        # Limited system
        elif ram_gb >= 4:
            return 'base'

        # Very limited system
        else:
            return 'tiny'

    def get_estimated_speed(self, model_name: str) -> str:
        """Get estimated transcription speed for the model on current hardware"""
        if model_name not in self.model_specs:
            return "Unknown"

        base_multiplier = self.model_specs[model_name]['speed_multiplier']
        gpu_info = self.system_info['gpu_info']

        # Adjust for GPU acceleration
        if gpu_info['has_gpu']:
            if gpu_info['gpu_type'] == 'nvidia' and self.system_info['cuda_available']:
                multiplier = base_multiplier * 3  # CUDA boost
            elif gpu_info['gpu_type'] == 'apple' and self.system_info['metal_available']:
                multiplier = base_multiplier * 2  # Metal boost
            else:
                multiplier = base_multiplier * 1.5  # Generic GPU boost
        else:
            multiplier = base_multiplier

        # Adjust for CPU
        cpu_factor = min(self.system_info['cpu_threads'] / 4, 2.0)  # Cap at 2x boost
        final_multiplier = multiplier * cpu_factor

        if final_multiplier >= 10:
            return f"~{int(final_multiplier)}x real-time"
        elif final_multiplier >= 2:
            return f"~{final_multiplier:.1f}x real-time"
        else:
            return f"~{final_multiplier:.1f}x real-time (slower than real-time)"

    def check_model_requirements(self, model_name: str) -> Dict:
        """Check if system meets requirements for the model"""
        if model_name not in self.model_specs:
            return {'compatible': False, 'issues': ['Unknown model']}

        spec = self.model_specs[model_name]
        issues = []

        # Check RAM
        required_ram_gb = spec['memory_mb'] / 1024
        if self.system_info['available_ram_gb'] < required_ram_gb:
            issues.append(f"Insufficient RAM: need {required_ram_gb:.1f}GB, have {self.system_info['available_ram_gb']:.1f}GB available")

        # Check disk space
        required_disk_gb = spec['size_mb'] / 1024
        if self.system_info['disk_free_gb'] < required_disk_gb + 1:  # +1GB buffer
            issues.append(f"Insufficient disk space: need {required_disk_gb:.1f}GB, have {self.system_info['disk_free_gb']:.1f}GB available")

        return {
            'compatible': len(issues) == 0,
            'issues': issues,
            'recommended': model_name == self.get_model_recommendation()
        }

    def get_hardware_summary(self) -> str:
        """Get formatted hardware summary for display"""
        gpu_info = self.system_info['gpu_info']
        lines = []

        # CPU info
        lines.append(f"CPU: {self.system_info['cpu_cores']} cores, {self.system_info['cpu_threads']} threads")

        # GPU info
        if gpu_info['has_gpu']:
            gpu_text = f"GPU: {gpu_info['gpu_name']}"
            if gpu_info['gpu_memory_gb'] > 0:
                gpu_text += f" ({gpu_info['gpu_memory_gb']}GB)"

            # Add acceleration info
            if gpu_info['gpu_type'] == 'nvidia' and self.system_info['cuda_available']:
                gpu_text += " [CUDA supported]"
            elif gpu_info['gpu_type'] == 'apple' and self.system_info['metal_available']:
                gpu_text += " [Metal supported]"
            else:
                gpu_text += " [Limited acceleration]"

            lines.append(gpu_text)
        else:
            lines.append("GPU: Not detected (CPU-only processing)")

        # RAM info
        lines.append(f"RAM: {self.system_info['ram_gb']}GB total, {self.system_info['available_ram_gb']}GB available")

        # Storage info
        lines.append(f"Storage: {self.system_info['disk_free_gb']}GB available")

        return "\n".join(lines)

    def get_all_models_info(self) -> List[Dict]:
        """Get information about all available models"""
        recommended = self.get_model_recommendation()
        models_info = []

        for name, spec in self.model_specs.items():
            requirements = self.check_model_requirements(name)
            speed = self.get_estimated_speed(name)

            models_info.append({
                'name': name,
                'size_mb': spec['size_mb'],
                'description': spec['description'],
                'use_case': spec['use_case'],
                'speed': speed,
                'compatible': requirements['compatible'],
                'issues': requirements['issues'],
                'recommended': name == recommended
            })

        return models_info

def test_hardware_detection():
    """Test the hardware detection system"""
    detector = HardwareDetector()

    print("Hardware Detection Test")
    print("=" * 40)
    print(detector.get_hardware_summary())
    print()

    print("Model Recommendations:")
    print("-" * 20)
    recommended = detector.get_model_recommendation()
    print(f"Recommended model: {recommended}")

    print("\nAll Models:")
    for model in detector.get_all_models_info():
        status = "[OK]" if model['compatible'] else "[FAIL]"
        rec = " (RECOMMENDED)" if model['recommended'] else ""
        print(f"{status} {model['name']}: {model['size_mb']}MB - {model['description']}{rec}")
        print(f"   Speed: {model['speed']}")
        if not model['compatible']:
            for issue in model['issues']:
                print(f"   Issue: {issue}")
        print()

if __name__ == "__main__":
    test_hardware_detection()