"""Lectura local y acotada de la telemetría que muestra HexOS."""
import os
from pathlib import Path
import subprocess
import threading
import time


# Sensores de temperatura de CPU conocidos: AMD (k10temp, zenpower) e Intel (coretemp).
CPU_SENSORS = ('k10temp', 'zenpower', 'coretemp')


class SystemTelemetry:
    """Muestra CPU, RAM y la GPU primaria sin mantener procesos residentes."""

    def __init__(self, hwmon=Path('/sys/class/hwmon'), loadavg=Path('/proc/loadavg'), cpuinfo=Path('/proc/cpuinfo')):
        self._lock = threading.Lock()
        self._previous_cpu = None
        self._hwmon = hwmon
        self._loadavg = loadavg
        self._cpuinfo = cpuinfo

    def _cpu_temperature(self):
        """La primera lectura del sensor de la CPU (Tctl en AMD, el paquete en Intel)."""
        try:
            for sensor in sorted(self._hwmon.iterdir()):
                if (sensor/'name').read_text().strip() in CPU_SENSORS:
                    return round(int((sensor/'temp1_input').read_text().strip()) / 1000, 1)
        except (OSError, ValueError):
            pass
        return None

    def _cpu_model(self):
        """El modelo y la frecuencia media actual de los núcleos, de /proc/cpuinfo."""
        name, frequencies = None, []
        try:
            for line in self._cpuinfo.read_text().splitlines():
                key, _, value = line.partition(':')
                key = key.strip()
                if key == 'model name' and name is None:
                    name = value.strip() or None
                elif key == 'cpu MHz':
                    frequencies.append(float(value))
        except (OSError, ValueError):
            pass
        return name, (round(sum(frequencies) / len(frequencies)) if frequencies else None)

    def _cpu_load(self):
        try:
            return round(float(self._loadavg.read_text().split()[0]), 2)
        except (OSError, ValueError, IndexError):
            return None

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
        name, frequency = self._cpu_model()
        return {'usage_pct': round(max(0.0, min(100.0, usage)), 1), 'cores': os.cpu_count(),
                'name': name, 'frequency_mhz': frequency,
                'load_1m': self._cpu_load(), 'temperature_c': self._cpu_temperature()}

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
