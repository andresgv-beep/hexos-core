"""Carga anticipada, barrera de ready y descarga ociosa sin GPU real."""
from pathlib import Path
import sys
import threading
import time
import unittest
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat_backend.model_lifecycle import ModelLifecycle
from hexos.agent.chat_backend.agent import Agent


class FakeRuntime:
    def __init__(self):
        self.thinking = False
        self.harvest_pending = False
        self.pending_image = None
        self.on_update = None
        self.messages = []
        self.kv_position = 0
        self.closed = False
        self.generated = []

    def begin_request(self, callback): self.on_update = callback
    def generate(self, messages):
        self.generated.append(messages)
        self.messages.extend(messages)
        return {'reply': 'Hola.', 'work': None}
    def call(self, request):
        self.messages = []
        self.kv_position = 0
        return {'ok': True}
    def close(self): self.closed = True
    def cancel(self): pass


def wait_for(predicate, timeout=1):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('timeout esperando el estado')


class ModelLifecycleTest(unittest.TestCase):
    def test_recupera_conversacion_archivada_tras_descargar(self):
        made = []
        lifecycle = ModelLifecycle(lambda: made.append(FakeRuntime()) or made[-1],
                                   ctx=32768, idle_seconds=.05)
        self.addCleanup(lifecycle.close)
        with tempfile.TemporaryDirectory() as workspace:
            agent = Agent(workspace, lifecycle)
            agent.chat('La palabra de prueba es albaricoque.')
            wait_for(lambda: lifecycle.status()['state'] == 'unloaded')
            agent.chat('Repite la palabra.')
            self.assertEqual(len(made), 2)
            self.assertIn('albaricoque', str(made[1].generated[0]))
            self.assertIn('Repite la palabra.', str(made[1].generated[0]))

    def test_cancelar_espera_no_envia_turno_tras_cargar(self):
        gate = threading.Event()
        runtime = FakeRuntime()
        lifecycle = ModelLifecycle(lambda: (gate.wait(2), runtime)[1], ctx=32768)
        self.addCleanup(lifecycle.close)
        with tempfile.TemporaryDirectory() as workspace:
            agent = Agent(workspace, lifecycle)
            result = []
            thread = threading.Thread(target=lambda: result.append(agent.chat('hola', request_id='cancel-load')))
            thread.start()
            wait_for(lambda: lifecycle.status()['state'] == 'loading')
            self.assertTrue(agent.cancel_generation('cancel-load')['ok'])
            thread.join(1)
            gate.set()
            self.assertFalse(thread.is_alive())
            self.assertTrue(result[0]['cancelled'])
            self.assertEqual(runtime.generated, [])

    def test_varios_avisos_comparten_una_sola_carga(self):
        gate = threading.Event()
        made = []
        def factory():
            made.append(FakeRuntime())
            gate.wait(1)
            return made[-1]
        lifecycle = ModelLifecycle(factory, ctx=32768)
        self.addCleanup(lifecycle.close)
        for _ in range(10): lifecycle.warmup()
        gate.set()
        wait_for(lambda: lifecycle.status()['ready'])
        self.assertEqual(len(made), 1)

    def test_arranca_sin_modelo_y_el_primer_caracter_calienta(self):
        made = []
        lifecycle = ModelLifecycle(lambda: made.append(FakeRuntime()) or made[-1],
                                   ctx=32768, idle_seconds=.2)
        self.addCleanup(lifecycle.close)
        self.assertEqual(lifecycle.status()['state'], 'unloaded')
        self.assertEqual(lifecycle.warmup()['state'], 'loading')
        wait_for(lambda: lifecycle.status()['ready'])
        self.assertEqual(len(made), 1)

    def test_un_turno_enviado_antes_de_ready_espera_la_carga(self):
        gate = threading.Event()
        runtime = FakeRuntime()
        def factory():
            gate.wait(1)
            return runtime
        lifecycle = ModelLifecycle(factory, ctx=32768, idle_seconds=.2)
        self.addCleanup(lifecycle.close)
        lifecycle.warmup()
        finished = threading.Event()
        def turn():
            lifecycle.acquire_turn()
            try: lifecycle.generate([{'role':'user', 'content':'hola'}])
            finally: lifecycle.release_turn(); finished.set()
        threading.Thread(target=turn, daemon=True).start()
        time.sleep(.03)
        self.assertFalse(finished.is_set(), 'el turno atravesó la barrera antes de ready')
        gate.set()
        self.assertTrue(finished.wait(1))
        self.assertEqual(runtime.generated[0][0]['content'], 'hola')

    def test_no_descarga_durante_turno_y_despues_libera_el_modelo(self):
        made = []
        lifecycle = ModelLifecycle(lambda: made.append(FakeRuntime()) or made[-1],
                                   ctx=32768, idle_seconds=.06)
        self.addCleanup(lifecycle.close)
        lifecycle.acquire_turn()
        time.sleep(.12)
        self.assertEqual(lifecycle.status()['state'], 'ready')
        lifecycle.release_turn()
        wait_for(lambda: lifecycle.status()['state'] == 'unloaded')
        self.assertTrue(made[0].closed)

    def test_tras_descargar_no_finge_conservar_el_kv(self):
        made = []
        lifecycle = ModelLifecycle(lambda: made.append(FakeRuntime()) or made[-1],
                                   ctx=32768, idle_seconds=.05)
        self.addCleanup(lifecycle.close)
        lifecycle.acquire_turn()
        lifecycle.generate([{'role':'user', 'content':'dato anterior'}])
        self.assertTrue(lifecycle.messages)
        lifecycle.release_turn()
        wait_for(lambda: lifecycle.status()['state'] == 'unloaded')
        self.assertEqual(lifecycle.messages, [])
        self.assertEqual(lifecycle.kv_position, 0)

    def test_un_error_de_carga_no_deja_el_turno_esperando_siempre(self):
        lifecycle = ModelLifecycle(lambda: (_ for _ in ()).throw(RuntimeError('sin VRAM')),
                                   ctx=32768, idle_seconds=.2)
        self.addCleanup(lifecycle.close)
        with self.assertRaisesRegex(RuntimeError, 'sin VRAM'):
            lifecycle.acquire_turn()


if __name__ == '__main__':
    unittest.main()
