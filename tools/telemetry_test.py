"""Telemetría de CPU: temperatura del sensor conocido y carga, sin inventar datos."""
from pathlib import Path
import tempfile
import unittest

from hexos.agent.telemetry import SystemTelemetry


class CpuTelemetryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hwmon = self.root/'hwmon'; self.hwmon.mkdir()
        self.loadavg = self.root/'loadavg'
        self.cpuinfo = self.root/'cpuinfo'

    def sensor(self, index, name, millidegrees):
        folder = self.hwmon/f'hwmon{index}'; folder.mkdir()
        (folder/'name').write_text(name+'\n')
        (folder/'temp1_input').write_text(f'{millidegrees}\n')

    def test_reads_the_cpu_sensor_and_skips_the_others(self):
        self.sensor(0, 'nvme', 38000)
        self.sensor(1, 'k10temp', 61750)
        self.loadavg.write_text('1.24 0.98 0.80 2/900 1234\n')
        self.cpuinfo.write_text('processor\t: 0\nmodel name\t: AMD Ryzen 7 5700X 8-Core Processor\ncpu MHz\t\t: 4000.0\n\n'
                                'processor\t: 1\nmodel name\t: AMD Ryzen 7 5700X 8-Core Processor\ncpu MHz\t\t: 4500.0\n')
        cpu = SystemTelemetry(self.hwmon, self.loadavg, self.cpuinfo)._cpu()
        self.assertEqual((cpu['temperature_c'], cpu['load_1m']), (61.8, 1.24))
        self.assertEqual((cpu['name'], cpu['frequency_mhz']), ('AMD Ryzen 7 5700X 8-Core Processor', 4250))
        self.assertGreaterEqual(cpu['cores'], 1)

    def test_missing_sensor_or_load_is_unknown_not_zero(self):
        self.sensor(0, 'nvme', 38000)
        cpu = SystemTelemetry(self.hwmon, self.root/'no-existe', self.root/'tampoco')._cpu()
        self.assertIsNone(cpu['temperature_c'])
        self.assertEqual((cpu['name'], cpu['frequency_mhz']), (None, None))
        self.assertIsNone(cpu['load_1m'])


if __name__ == '__main__':
    unittest.main()
