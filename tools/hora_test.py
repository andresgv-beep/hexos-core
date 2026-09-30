"""La hora local llega al modelo al empezar y tras una pausa, sin tocar los turnos seguidos."""
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from hexos.agent.chat import Agent
from hexos.agent.chat_backend.context import hora_local


class Native:
    native = True

    def __init__(self):
        self.messages, self.inputs, self.turns = [], [], []

    def generate(self, messages):
        if not self.messages:
            self.messages = list(messages)
        else:
            self.messages.extend(messages)
        self.inputs.append(messages[-1]['content'])
        self.turns.append(repr(messages))
        self.messages.append(dict(role='assistant', content='Vale.'))
        return dict(reply='Vale.', work=None)

    def call(self, request):
        self.messages = []


class HoraTest(unittest.TestCase):
    def test_formato(self):
        noche = datetime(2026, 9, 30, 23, 40, tzinfo=ZoneInfo('Europe/Madrid'))
        self.assertIn('miércoles 30 de septiembre de 2026, 23:40', hora_local(noche))

    def test_apagada_por_defecto(self):
        with tempfile.TemporaryDirectory() as workspace, mock.patch.dict(os.environ, {'HEXOS_HORA': ''}):
            runtime = Native()
            Agent(workspace, runtime).chat('hola')
            self.assertNotIn('HORA LOCAL', runtime.turns[-1])

    @mock.patch.dict(os.environ, {'HEXOS_HORA': '1'})
    def test_al_empezar_y_tras_una_pausa_pero_no_en_turnos_seguidos(self):
        with tempfile.TemporaryDirectory() as workspace:
            runtime = Native()
            agent = Agent(workspace, runtime)
            agent.chat('hola')
            self.assertIn('HORA LOCAL', runtime.turns[-1])        # contexto nuevo: va en las referencias
            agent.chat('pues hazlo')
            self.assertEqual(runtime.inputs[-1], 'pues hazlo')     # literal: acaba de hablar
            hace_media_hora = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            with agent.store() as store:
                store.db.execute("UPDATE conversation SET ts=? WHERE role='user'", (hace_media_hora,))
                store.db.commit()
            agent.chat('me voy a dormir')
            self.assertIn('HORA LOCAL', runtime.inputs[-1])
            self.assertTrue(runtime.inputs[-1].endswith('me voy a dormir'))


if __name__ == '__main__':
    unittest.main()
