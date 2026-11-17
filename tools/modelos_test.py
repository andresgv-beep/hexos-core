"""Lista de modelos y cambio en caliente, sin GPU real."""
from pathlib import Path
import json
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat_backend import modelos
from hexos.agent.chat_backend.model_lifecycle import ModelLifecycle


class FakeRuntime:
    def __init__(self, nombre):
        self.nombre = nombre
        self.thinking = False
        self.harvest_pending = False
        self.pending_image = None
        self.on_update = None
        self.messages = []
        self.kv_position = 0
        self.closed = False

    def generate(self, messages):
        return {'reply': self.nombre, 'work': None}

    def close(self):
        self.closed = True

    def cancel(self):
        pass


def espera(predicado, segundos=2):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if predicado():
            return True
        time.sleep(0.01)
    return False


class ListaTest(unittest.TestCase):
    def fichero(self, contenido):
        ruta = Path(self.carpeta.name) / 'modelos.json'
        ruta.write_text(contenido if isinstance(contenido, str) else json.dumps(contenido))
        return ruta

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)

    def uno(self, **cambios):
        return dict(dict(id='a', nombre='A', hnf='/x/a.hnf', plantilla='/x/a.jinja', ctx=4096), **cambios)

    def test_lee_una_lista_valida_en_su_orden(self):
        lista = modelos.leer(self.fichero({'modelos': [self.uno(), self.uno(id='b', nombre='B', pensamiento=True)]}))
        self.assertEqual([m['id'] for m in lista], ['a', 'b'])

    def test_rechaza_lo_que_dejaria_el_servicio_a_medias(self):
        for malo in ('{', {'modelos': []}, {'otra': 1},
                     {'modelos': [self.uno(), self.uno()]},                 # id repetido
                     {'modelos': [self.uno(id='Con Espacios')]},
                     {'modelos': [self.uno(ctx='4096')]},
                     {'modelos': [self.uno(ctx=100)]},
                     {'modelos': [self.uno(sobra=1)]},
                     {'modelos': [{k: v for k, v in self.uno().items() if k != 'plantilla'}]}):
            with self.assertRaises(ValueError, msg=repr(malo)):
                modelos.leer(self.fichero(malo))

    def test_un_fichero_que_no_esta_no_es_un_error_de_json_sin_explicar(self):
        with self.assertRaisesRegex(ValueError, 'No pude leer la lista de modelos'):
            modelos.leer(Path(self.carpeta.name) / 'no-existe.json')


class CambioTest(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        base = Path(self.carpeta.name)
        self.lista = []
        for nombre, ctx in (('uno', 4096), ('dos', 8192)):
            (base / (nombre + '.hnf')).write_text('x')
            (base / (nombre + '.jinja')).write_text('x')
            self.lista.append(dict(id=nombre, nombre=nombre.upper(), hnf=str(base / (nombre + '.hnf')),
                                   plantilla=str(base / (nombre + '.jinja')), ctx=ctx))
        self.cargados = []

        def fabrica(modelo):
            def cargar():
                runtime = FakeRuntime(modelo['id'])
                self.cargados.append(runtime)
                return runtime
            return cargar
        self.catalogo = modelos.Modelos(self.lista, fabrica)
        self.runtime = ModelLifecycle(self.catalogo.fabrica(), ctx=self.lista[0]['ctx'], idle_seconds=600)
        self.addCleanup(self.runtime.close)

    def cargar(self):
        self.runtime.warmup()
        self.assertTrue(espera(lambda: self.runtime.status()['ready']))

    def test_el_primero_es_el_de_arranque_y_la_lista_dice_cual_esta_puesto(self):
        self.assertEqual(self.catalogo.activo, 'uno')
        self.assertEqual([(m['id'], m['active'], m['available']) for m in self.catalogo.lista()],
                         [('uno', True, True), ('dos', False, True)])

    def test_cambiar_descarga_el_anterior_y_el_siguiente_que_carga_es_el_nuevo(self):
        self.cargar()
        anterior = self.cargados[-1]
        self.assertTrue(self.catalogo.elegir('dos', self.runtime))
        self.assertTrue(anterior.closed)
        self.assertEqual(self.runtime.status()['state'], 'unloaded')
        self.assertEqual(self.runtime.ctx, 8192)
        self.cargar()
        self.assertEqual(self.cargados[-1].nombre, 'dos')
        self.assertEqual(self.runtime.generate([])['reply'], 'dos')

    def test_elegir_el_que_ya_esta_no_descarga_nada(self):
        self.cargar()
        self.assertFalse(self.catalogo.elegir('uno', self.runtime))
        self.assertFalse(self.cargados[-1].closed)
        self.assertTrue(self.runtime.status()['ready'])

    def test_sin_modelo_cargado_solo_cambia_cual_se_cargara(self):
        self.assertTrue(self.catalogo.elegir('dos', self.runtime))
        self.assertEqual(self.cargados, [])
        self.cargar()
        self.assertEqual(self.cargados[-1].nombre, 'dos')

    def test_un_modelo_que_no_existe_o_cuyo_fichero_falta_no_toca_el_que_hay(self):
        self.cargar()
        with self.assertRaisesRegex(ValueError, 'No hay ningún modelo'):
            self.catalogo.elegir('tres', self.runtime)
        Path(self.lista[1]['hnf']).unlink()
        self.assertFalse(self.catalogo.lista()[1]['available'])
        with self.assertRaisesRegex(ValueError, 'no está disponible'):
            self.catalogo.elegir('dos', self.runtime)
        self.assertEqual(self.catalogo.activo, 'uno')
        self.assertFalse(self.cargados[-1].closed)
        self.assertTrue(self.runtime.status()['ready'])

    def test_con_un_turno_en_marcha_no_se_cambia(self):
        self.cargar()
        self.runtime.acquire_turn()
        try:
            with self.assertRaisesRegex(RuntimeError, 'turno en marcha'):
                self.catalogo.elegir('dos', self.runtime)
        finally:
            self.runtime.release_turn()
        self.assertEqual(self.catalogo.activo, 'uno')
        self.assertFalse(self.cargados[-1].closed)

    def test_guardado_y_restaurado_por_el_agente(self):
        from hexos.agent.chat_backend.agent import Agent
        agente = Agent(self.carpeta.name + '/ws', self.runtime)
        agente.modelos = self.catalogo
        self.assertEqual(agente.models_snapshot()['active'], 'uno')
        resultado = agente.select_model('dos')
        self.assertTrue(resultado['changed'])
        self.assertEqual(resultado['active'], 'dos')
        self.assertTrue(espera(lambda: self.runtime.status()['ready']))
        # Un servicio nuevo arranca con el primero de la lista y recupera el elegido.
        otro = modelos.Modelos(self.lista, lambda m: (lambda: FakeRuntime(m['id'])))
        nuevo = ModelLifecycle(otro.fabrica(), ctx=4096, idle_seconds=600)
        self.addCleanup(nuevo.close)
        agente2 = Agent(self.carpeta.name + '/ws', nuevo)
        agente2.modelos = otro
        self.assertEqual(agente2.restore_model(), 'dos')
        self.assertEqual(nuevo.ctx, 8192)


if __name__ == '__main__':
    unittest.main()
