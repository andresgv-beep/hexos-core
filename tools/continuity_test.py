"""Pruebas de recuperación; no certifican el comportamiento del modelo."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.continuity import HeraProfile

ROOT = Path(__file__).resolve().parents[1]

class Runtime:
    def call(self, request): pass
    def generate(self, messages):
        self.messages = messages
        return {'reply': 'Recibido', 'work': None}

class ContinuityTest(unittest.TestCase):
    def test_history_survives_reset_and_pages_exactly(self):
        with tempfile.TemporaryDirectory() as home:
            a = Agent(home, Runtime())
            raw = 'inicio único ' + 'x' * 14000 + ' FINAL'
            a.chat(raw)
            a.clear_context()
            b = Agent(home, Runtime())
            with b.store() as s:
                hit = b.tool(s, 'history.search', {'query': 'inicio único'})['matches'][0]
                out = ''; start = 0
                while start is not None:
                    page = b.tool(s, 'history.read', {'id':hit['id'], 'start':start})
                    out += page['text']; start = page['next_start']
                self.assertEqual(out, raw)
                self.assertEqual(b.tool(s, 'history.search', {'query':'%'})['matches'], [])
            with tempfile.TemporaryDirectory() as other:
                c = Agent(other, Runtime())
                with c.store() as s:
                    self.assertEqual(c.tool(s, 'history.search', {'query':'inicio único'})['matches'], [])

    def test_profile_confirmed_correction_and_read_no_append(self):
        binary = ROOT / 'hera/bin/hera'
        self.assertTrue(binary.exists(), 'compilar con make -C hera cli')
        with tempfile.TemporaryDirectory() as home:
            def cli(*args):
                return subprocess.check_output([str(binary), *args],
                    env=dict(os.environ, HELIOS_HOME=home), text=True).strip()
            ev = cli('dijo', 'guarda esto: mi nombre es Ana')
            cli('guarda', 'yo/nombre', 'Ana', 'Su nombre es Ana', ev)
            candidate = cli('dijo', 'vivo en Bilbao')
            cli('propon', 'yo/ciudad', 'Bilbao', 'Vive en Bilbao', candidate)
            profile = HeraProfile(binary, home)
            self.assertIn('Ana', profile.read())
            self.assertNotIn('Bilbao', profile.read())
            correction = cli('dijo', 'corrige mi nombre: soy Andrés')
            cli('corrige', 'yo/nombre', 'Andrés', 'Su nombre es Andrés', correction, correction)
            before = (Path(home) / 'hera.jsonl').read_bytes()
            text = profile.read()
            self.assertIn('Andrés', text); self.assertNotIn('Ana', text)
            self.assertEqual(before, (Path(home) / 'hera.jsonl').read_bytes())
            with tempfile.TemporaryDirectory() as workspace:
                runtime = Runtime()
                a = Agent(workspace, runtime, profile)
                a.clear_context(); a.chat('¿Cómo me llamo?')
                self.assertIn('Su nombre es Andrés', runtime.messages[-1]['content'])

    def test_failed_profile_is_not_silent(self):
        class Broken:
            def read(self): raise RuntimeError('memoria rota')
        with tempfile.TemporaryDirectory() as home:
            a = Agent(home, Runtime(), Broken())
            with self.assertRaisesRegex(RuntimeError, 'memoria rota'):
                a.chat('hola')

if __name__ == '__main__': unittest.main()
