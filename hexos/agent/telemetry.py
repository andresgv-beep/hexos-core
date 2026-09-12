"""Lectura local y acotada de la telemetría que muestra HexOS."""
from pathlib import Path
import subprocess
import threading
import time


class SystemTelemetry:
    """Muestra CPU, RAM y la GPU primaria sin mantener procesos residentes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._previous_cpu = None

    @staticmethod
    def _memory():
        values = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            name, _, raw = line.partition(':')
            if name in ('MemTotal', 'MemAvailable'):
                values[name] = int(raw.strip().split()[0]) // 1024
        total = values.get('MemTotal', 0)
        available = values.get('MemAvailable', 0)
        return {'used_mb': max(0, total - available), 'total_mb': total}

    def _cpu(self):
        fields = [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        total = sum(fields)
        usage = 0.0
        if self._previous_cpu:
            old_idle, old_total = self._previous_cpu
            elapsed = total - old_total
            if elapsed > 0:
                usage = 100.0 * (1.0 - (idle - old_idle) / elapsed)
        self._previous_cpu = (idle, total)
        return {'usage_pct': round(max(0.0, min(100.0, usage)), 1)}

    @staticmethod
    def _gpu():
        command = [
            'nvidia-smi',
            '--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
            '--format=csv,noheader,nounits',
        ]
        try:
            line = subprocess.run(command, capture_output=True, text=True, timeout=2,
                                  check=True).stdout.splitlines()[0]
            name, usage, used, total, temperature, power = [part.strip() for part in line.split(',', 5)]
            return {
                'gpu': {'name': name, 'usage_pct': float(usage), 'temperature_c': float(temperature),
                        'power_w': float(power), 'healthy': True},
                'vram': {'used_mb': int(used), 'total_mb': int(total)},
            }
        except (FileNotFoundError, IndexError, subprocess.SubprocessError, ValueError):
            return {
                'gpu': {'name': 'GPU no disponible', 'usage_pct': 0.0, 'temperature_c': None,
                        'power_w': None, 'healthy': False},
                'vram': {'used_mb': 0, 'total_mb': 0},
            }

    def snapshot(self):
        with self._lock:
            return {
                'timestamp_ms': int(time.time() * 1000),
                'cpu': self._cpu(),
                'ram': self._memory(),
                **self._gpu(),
            }
