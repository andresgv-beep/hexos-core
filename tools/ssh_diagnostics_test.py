import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from hexos.agent.ssh_diagnostics import diagnose


class SSHDiagnosticsTest(unittest.TestCase):
    def test_requires_configuration_and_fixed_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): diagnose(tmp,'kernel; reboot')
            with self.assertRaises(ValueError): diagnose(tmp,'kernel')

    def test_fixed_command_strict_host_checking_and_bounded_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'key').touch(); (root/'hosts').touch()
            (root/'synology_ssh.json').write_text(json.dumps(dict(host='192.168.1.243',user='tester',
                identity_file=str(root/'key'),known_hosts_file=str(root/'hosts'))))
            def run(argv, **kw):
                self.assertEqual(argv[-1],'dmesg')
                self.assertIn('StrictHostKeyChecking=yes',argv)
                self.assertIn('BatchMode=yes',argv)
                self.assertNotIn('shell',kw)
                kw['stdout'].write(b'x'*17000)
                kw['stderr'].write(b'permission denied')
                return SimpleNamespace(returncode=1)
            with patch('hexos.agent.ssh_diagnostics.shutil.which',return_value='/usr/bin/ssh'), patch('hexos.agent.ssh_diagnostics.subprocess.run',side_effect=run):
                r=diagnose(root,'kernel')
            self.assertEqual(r['exit_code'],1)
            self.assertTrue(r['truncated'])
            self.assertEqual(len(r['stdout']),16000)
            self.assertIn('permission denied',r['stderr'])
