"""Chat y Agente no comparten conversación ni contexto: cada ventana tiene los suyos."""
import json
import tempfile
import unittest
from uuid import uuid4

from hexos.agent.chat import Agent
from hexos.agent.chat_backend.history_archive import history_page
from hexos.agent.continuity import history_tool
from hexos.agent.work import now


class Runtime:
    def __init__(self):
        self.vistos, self.llamadas = [], []

    def call(self, request):
        self.llamadas.append(request)

    def generate(self, messages):
        self.vistos.append(json.dumps(messages, ensure_ascii=False))
        return {'reply': 'Hecho.', 'work': None}


class VentanasSeparadasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-ventanas-')
        self.runtime = Runtime()
        self.agente = Agent(self.tmp.name, self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def textos(self):
        with self.agente.store() as store:
            return [m['text'] for m in history_page(store)['messages']]

    def test_cada_ventana_ve_solo_lo_suyo(self):
        self.agente.set_window('chat')
        self.agente.chat('apunta que el martes hay cena')
        self.agente.set_window('agente')
        self.agente.chat('cuanta memoria queda')
        self.assertEqual(self.textos(), ['cuanta memoria queda', 'Hecho.'])
        self.agente.set_window('chat')
        self.assertEqual(self.textos(), ['apunta que el martes hay cena', 'Hecho.'])

    def test_al_modelo_no_le_llega_la_otra_conversacion(self):
        self.agente.set_window('chat')
        self.agente.chat('apunta que el martes hay cena')
        self.agente.set_window('agente')
        self.runtime.vistos.clear()
        self.agente.chat('cuanta memoria queda')
        self.assertNotIn('martes', '\n'.join(self.runtime.vistos))

    def test_al_volver_se_recupera_la_conversacion_de_esa_ventana(self):
        self.agente.set_window('chat')
        self.agente.chat('apunta que el martes hay cena')
        self.agente.set_window('agente')
        self.agente.chat('cuanta memoria queda')
        self.agente.set_window('chat')
        self.runtime.vistos.clear()
        self.agente.chat('y a que hora era')
        visto = '\n'.join(self.runtime.vistos)
        self.assertIn('martes', visto)
        self.assertNotIn('cuanta memoria', visto)

    def test_cambiar_de_ventana_vacia_el_contexto_del_modelo(self):
        self.agente.set_window('chat')
        self.runtime.llamadas.clear()
        self.agente.set_window('agente')
        self.assertIn({'type': 'reset'}, self.runtime.llamadas)

    def test_pulsar_la_misma_ventana_no_tira_el_contexto(self):
        self.agente.set_window('agente')
        self.runtime.llamadas.clear()
        self.agente.set_window('agente')
        self.assertEqual(self.runtime.llamadas, [])

    def test_no_se_cambia_a_mitad_de_turno(self):
        self.agente.set_window('chat')
        self.agente.lock.acquire()
        try:
            with self.assertRaises(RuntimeError):
                self.agente.set_window('agente')
        finally:
            self.agente.lock.release()
        self.assertEqual(self.agente.ventana, 'chat')

    def test_lo_anterior_a_separarlas_se_queda_en_el_chat(self):
        # Un mensaje sin apunte de ventana: así está todo el historial que ya existía.
        with self.agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uuid4().hex, now(), 'user', 'mensaje viejo', 'mensaje viejo'))
            store.db.execute('DELETE FROM conversation_ventana')
            store.db.commit()
        self.agente.set_window('chat')
        self.assertEqual(self.textos(), ['mensaje viejo'])
        self.agente.set_window('agente')
        self.assertEqual(self.textos(), [])

    def test_limpiar_el_contexto_de_una_no_corta_la_otra(self):
        self.agente.set_window('chat')
        self.agente.chat('apunta que el martes hay cena')
        self.agente.set_window('agente')
        self.agente.chat('cuanta memoria queda')
        self.agente.clear_context()
        self.agente.set_window('chat')
        self.runtime.vistos.clear()
        self.agente.chat('y a que hora era')
        self.assertIn('martes', '\n'.join(self.runtime.vistos))

    def test_el_archivo_que_busca_el_modelo_es_el_de_su_ventana(self):
        self.agente.set_window('chat')
        self.agente.chat('apunta que el martes hay cena')
        self.agente.set_window('agente')
        with self.agente.store() as store:
            self.assertEqual(history_tool(store, 'history.search', {'query': 'martes'})['matches'], [])
            self.assertEqual(history_tool(store, 'history.recent', {})['messages'], [])


if __name__ == '__main__':
    unittest.main()
