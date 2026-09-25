"""Regression: NAS reports must not receive unsolicited personal profile facts."""
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import TurnState, AgentDependencies
from hexos.agent import catalog

class Runtime:
    native = True
    ctx = 16384
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}

class Profile:
    def read(self): raise AssertionError('Whole personal profile must not be injected')
    def keys(self): return {'yo/oficio': 'electricista', 'yo/mascota': 'SecretoMascota'}

class ReportContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        def nas(workspace, **args):
            self.calls.append(args)
            return {'containers': [], 'total': 0}
        self.agent = Agent(self.tmp.name, Runtime(), Profile(),
                           dependencies=AgentDependencies(nas_read=nas))

    def test_profile_not_in_native_or_json_report_context(self):
        for native in (True, False):
            self.agent.runtime.native = native
            with self.agent.store() as store:
                turn = TurnState(text='haz un resumen de todo y crealo como nota')
                self.agent.context.prepare(store, turn)
                text = json.dumps(turn.messages, ensure_ascii=False)
                self.assertNotIn('SecretoMascota', text)
                self.assertNotIn('electricista', text)
                self.assertIn('profile_recall', text)

    def test_continuing_turns_do_not_accumulate_static_context(self):
        runtime = self.agent.runtime
        runtime.messages = []
        with self.agent.store() as store, patch(
                'hexos.agent.chat_backend.media_tools.load',
                side_effect=AssertionError('Unrelated chat must not load media config')):
            first = TurnState(text='hola socio')
            self.agent.context.prepare(store, first)
            self.assertIn('profile_recall', json.dumps(first.messages))
            runtime.messages = list(first.messages)
            for text in ('recetas de pollo', 'busca', 'busca en la web'):
                turn = TurnState(text=text)
                self.agent.context.prepare(store, turn)
                self.assertEqual(turn.messages, [dict(role='user', content=text)])
                runtime.messages.extend(turn.messages)
            combined = json.dumps(runtime.messages, ensure_ascii=False)
            self.assertEqual(combined.count('MEMORIA PERSONAL:'), 1)
            self.assertNotIn('BIBLIOTECAS DE PELÍCULAS', combined)
            # Reload restores the capability hint once, without losing dialogue.
            runtime.messages = []
            rebuilt = TurnState(text='seguimos')
            self.agent.context.prepare(store, rebuilt)
            content = json.dumps(rebuilt.messages, ensure_ascii=False)
            self.assertEqual(content.count('MEMORIA PERSONAL:'), 1)
            self.assertIn('recetas de pollo', content)

    def test_recall_only_delivers_matching_facts(self):
        self.assertIn('profile.recall', catalog.model_tools())
        with self.agent.store() as store:
            result = self.agent.dispatcher.dispatch(store, 'profile.recall', {'query':'ofício'})
            self.assertEqual(result['facts'], [{'key':'yo/oficio','value':'electricista'}])
            with self.assertRaises(ValueError):
                self.agent.dispatcher.dispatch(store, 'profile.recall', {'query':'*'})

    def test_ambiguous_all_never_reaches_ssh(self):
        with self.agent.store() as store:
            with self.assertRaisesRegex(ValueError, 'scope=all'):
                self.agent.dispatcher.dispatch(store, 'nas.read',
                    {'device':'fixture','section':'containers','container':'all'})
        self.assertEqual(self.calls, [])

    def test_global_and_filtered_results_have_explicit_scope(self):
        with self.agent.store() as store:
            for args, all_devices in [({'scope':'all'}, True),
                                      ({'container':'plex'}, False),
                                      ({'scope':'name','container':'all'}, False)]:
                result = self.agent.dispatcher.dispatch(store, 'nas.read',
                    dict(device='fixture',section='containers',**args))
                self.assertEqual(result['scope']['covers_all_containers'], all_devices)
                self.assertNotIn('scope', self.calls[-1])
                if not all_devices:self.assertIn('no demuestra ausencia',result['scope_note'])
            with self.assertRaises(ValueError):
                self.agent.dispatcher.dispatch(store,'nas.read',dict(device='fixture',section='containers',scope='all',container='plex'))

if __name__ == '__main__': unittest.main()
