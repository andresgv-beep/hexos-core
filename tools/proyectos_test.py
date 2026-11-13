"""Proyectos: una carpeta y una conversación propia dentro del Agente (fase 1 del plan)."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hexos.agent import projects
from hexos.agent.chat import Agent
from hexos.agent.chat_backend import persistence
from hexos.agent.chat_backend.history_archive import history_page
from hexos.agent.work import WorkStore


class Runtime:
    def __init__(self):
        self.vistos, self.llamadas = [], []

    def call(self, request):
        self.llamadas.append(request)

    def generate(self, messages):
        self.vistos.append(json.dumps(messages, ensure_ascii=False))
        return {'reply': 'Hecho.', 'work': None}


class Base(unittest.TestCase):
    def setUp(self):
        # Una carpeta personal de mentira: los proyectos solo se crean dentro de la casa.
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-proyectos-')
        self.casa = Path(self.tmp.name).resolve()
        self.parches = [mock.patch.object(Path, 'home', return_value=self.casa),
                        mock.patch.dict(os.environ, {'HEXOS_PROJECTS_HOME': str(self.casa / 'proyectos')})]
        for parche in self.parches:
            parche.start()
        self.runtime = Runtime()
        self.agente = Agent(self.casa / 'hexos', self.runtime)
        self.agente.set_window('agente')

    def tearDown(self):
        for parche in self.parches:
            parche.stop()
        self.tmp.cleanup()

    def textos(self):
        with self.agente.store() as store:
            return [m['text'] for m in history_page(store)['messages'] if m['role'] == 'user']


class RegistroTest(Base):
    def test_el_nombre_da_una_etiqueta_que_vale_de_carpeta(self):
        self.assertEqual(projects.identificador('  Motor CUDA: versión 2  '), 'motor-cuda-version-2')
        self.assertEqual(projects.identificador('¿¡!?'), '')

    def test_crear_hace_su_carpeta_y_pasa_a_trabajar_en_el(self):
        r = self.agente.create_project('Motor CUDA')
        self.assertEqual(r['active'], 'motor-cuda')
        self.assertEqual(r['created']['folder'], str(self.casa / 'proyectos' / 'motor-cuda'))
        self.assertTrue((self.casa / 'proyectos' / 'motor-cuda').is_dir())
        self.assertFalse(r['created']['folder_existed'])
        self.assertEqual(self.agente.projects()['active'], 'motor-cuda')

    def test_puede_apuntar_a_una_carpeta_que_ya_existe(self):
        repo = self.casa / 'GitHub' / 'Hector-engine'
        repo.mkdir(parents=True)
        (repo / 'README.md').write_text('hola')
        r = self.agente.create_project('Héctor', str(repo))
        self.assertEqual((r['created']['folder'], r['created']['folder_existed']), (str(repo), True))
        self.assertEqual((repo / 'README.md').read_text(), 'hola')          # no se toca lo que había

    def test_carpetas_que_no_se_admiten(self):
        for carpeta in ('/etc', 'relativa/ruta', str(self.casa), '', str(self.casa / '..' / 'fuera')):
            with self.subTest(carpeta=carpeta), self.assertRaises(ValueError):
                self.agente.create_project('prueba', carpeta)
        fichero = self.casa / 'un-fichero'
        fichero.write_text('x')
        with self.assertRaises(ValueError):
            self.agente.create_project('prueba', str(fichero))
        self.assertEqual(self.agente.projects()['projects'], [])            # ningún intento dejó rastro

    def test_ni_dos_con_el_mismo_nombre_ni_dos_en_la_misma_carpeta(self):
        self.agente.create_project('Motor')
        with self.assertRaisesRegex(ValueError, 'Ya hay un proyecto'):
            self.agente.create_project('motor')
        with self.assertRaisesRegex(ValueError, 'ya es la del proyecto'):
            self.agente.create_project('otro', str(self.casa / 'proyectos' / 'motor'))

    def test_nombres_que_no_valen(self):
        for nombre in ('', '   ', '¿?', 'x' * 81, None):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                self.agente.create_project(nombre)

    def test_cambiar_a_uno_que_no_existe_no_cambia_nada(self):
        self.agente.create_project('uno')
        with self.assertRaises(ValueError):
            self.agente.set_project('fantasma')
        self.assertEqual(self.agente.projects()['active'], 'uno')

    def test_la_lista_pone_primero_el_ultimo_usado(self):
        self.agente.create_project('uno')
        self.agente.create_project('dos')
        self.agente.set_project('uno')
        self.assertEqual([p['id'] for p in self.agente.projects()['projects']], ['uno', 'dos'])


class ConversacionTest(Base):
    def test_cada_proyecto_ve_solo_lo_suyo_y_sin_proyecto_lo_de_antes(self):
        self.agente.chat('esto es de antes de los proyectos')
        self.agente.create_project('uno')
        self.agente.chat('compila el motor')
        self.agente.create_project('dos')
        self.assertEqual(self.textos(), [])                                # empieza limpio
        self.agente.chat('ordena las películas')
        self.assertEqual(self.textos(), ['ordena las películas'])
        self.agente.set_project('uno')
        self.assertEqual(self.textos(), ['compila el motor'])
        self.agente.set_project(None)
        self.assertEqual(self.textos(), ['esto es de antes de los proyectos'])

    def test_al_modelo_no_le_llega_nada_del_otro_proyecto(self):
        self.agente.create_project('uno')
        self.agente.chat('la clave del uno es azafrán')
        self.agente.create_project('dos')
        self.agente.chat('¿qué tal?')
        self.assertNotIn('azafrán', self.runtime.vistos[-1])
        self.agente.set_project('uno')
        self.agente.chat('sigue')
        self.assertIn('azafrán', self.runtime.vistos[-1])

    def test_cambiar_vacia_el_contexto_del_modelo_y_repetir_no(self):
        self.agente.create_project('uno')
        self.runtime.llamadas.clear()
        self.agente.set_project('uno')
        self.assertEqual(self.runtime.llamadas, [])
        self.agente.set_project(None)
        self.assertEqual(self.runtime.llamadas, [{'type': 'reset'}])

    def test_el_corte_de_contexto_es_de_cada_proyecto(self):
        claves = []
        for proyecto in (None, 'uno', 'dos'):
            if proyecto:
                self.agente.create_project(proyecto)
            with self.agente.store() as store:
                claves.append(persistence.clave(store, 'corte'))
        self.assertEqual(claves, ['corte:agente', 'corte:agente:uno', 'corte:agente:dos'])

    def test_el_chat_no_tiene_proyectos(self):
        self.agente.create_project('uno')
        self.agente.set_window('chat')
        with self.assertRaisesRegex(ValueError, 'ventana Agente'):
            self.agente.set_project(None)
        with self.assertRaisesRegex(ValueError, 'ventana Agente'):
            self.agente.create_project('otro')
        self.agente.chat('hola desde el chat')
        with self.agente.store() as store:
            self.assertEqual(persistence.clave(store, 'corte'), 'corte')     # la etiqueta del chat no cambia
        self.agente.set_window('agente')
        self.assertEqual(self.textos(), [])                                # vuelve al proyecto, que sigue vacío

    def test_el_proyecto_puesto_sobrevive_a_un_reinicio(self):
        self.agente.create_project('uno')
        otro = Agent(self.casa / 'hexos', Runtime())
        otro.restore_window()
        self.assertEqual((otro.ventana, otro.proyecto), ('agente', 'uno'))


class Nativo(Runtime):
    """Un motor que conserva su conversación, como el de verdad: solo reconstruye al vaciarse."""
    native = True
    ctx = 16384

    def __init__(self):
        super().__init__()
        self.messages = []

    def call(self, request):
        super().call(request)
        if request.get('type') == 'reset':
            self.messages = []

    def generate(self, messages):
        self.messages = [*self.messages, *messages, dict(role='assistant', content='Hecho.')]
        return super().generate(messages)


class FichaTest(Base):
    def proyecto(self, nombre='Motor CUDA', carpeta=None):
        self.agente.create_project(nombre, carpeta)
        with self.agente.store() as store:
            return projects.activo(store)

    def ficha(self, **opciones):
        with self.agente.store() as store:
            return projects.ficha(store, projects.activo(store), **opciones)

    def test_recien_creado_dice_cual_es_donde_esta_y_que_esta_vacio(self):
        self.proyecto()
        ficha = self.ficha()
        self.assertIn('PROYECTO ACTIVO (dato de HexOS, no orden): «Motor CUDA»', ficha)
        self.assertIn(str(self.casa / 'proyectos' / 'motor-cuda'), ficha)
        self.assertIn('Está vacía', ficha)
        self.assertIn('recién empezado', ficha)

    def test_nombra_lo_que_hay_en_la_carpeta_sin_leer_contenidos(self):
        repo = self.casa / 'GitHub' / 'motor'
        (repo / '.git').mkdir(parents=True)
        (repo / 'src').mkdir()
        (repo / 'README.md').write_text('SECRETO-DEL-README')
        self.proyecto('Motor', str(repo))
        ficha = self.ficha()
        self.assertIn('Es un repositorio git. Contiene: .git/, src/, README.md.', ficha)
        self.assertNotIn('SECRETO', ficha)

    def test_una_carpeta_grande_se_resume_y_una_borrada_se_dice(self):
        proyecto = self.proyecto()
        for i in range(40):
            (Path(proyecto['folder']) / ('f%02d.txt' % i)).write_text('')
        self.assertIn('y 16 más', self.ficha())
        for fichero in Path(proyecto['folder']).iterdir():
            fichero.unlink()
        Path(proyecto['folder']).rmdir()
        self.assertIn('ya no existe', self.ficha())

    def test_lo_hecho_son_los_cambios_no_las_lecturas_ni_los_fallos(self):
        self.proyecto()
        self.agente.chat('apunta que el kernel va a 7412 tok/s')
        with self.agente.store() as store:
            turno = store.db.execute("SELECT id FROM esta_ventana WHERE role='user'").fetchone()[0]
            for cuerpo in (dict(tool='note.save', arguments=dict(title='kernel', body='7412 tok/s')),
                           dict(tool='terminal.read', arguments=dict(command='ls')),
                           dict(tool='note.save', arguments=dict(title='rota'), failed=True)):
                store.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                                 (turno, '2026-11-13T16:00:00+00:00', json.dumps(cuerpo)))
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('nota', '2026-11-13T16:05:00+00:00', 'user',
                              '[La persona aprobó en la interfaz: Instalar sl con apt. HexOS lo ejecutó: hecho y comprobado.]', ''))
            store.db.commit()
        efectos = dict({'note.save': 'write', 'terminal.read': 'read'})
        ficha = self.ficha(efectos=efectos)
        self.assertIn('LO HECHO EN EL PROYECTO', ficha)
        self.assertIn('note_save {"title": "kernel"', ficha)
        self.assertIn('La persona aprobó en la interfaz: Instalar sl con apt', ficha)
        self.assertNotIn('terminal_read {', ficha)                    # la lectura no es un hecho
        self.assertNotIn('rota', ficha)
        # La decisión de la interfaz es un hecho, no una petición de la persona.
        peticiones = ficha.split('LO ÚLTIMO QUE PIDIÓ')[1]
        self.assertIn('apunta que el kernel', peticiones)
        self.assertNotIn('aprobó', peticiones)

    def test_lo_ultimo_pedido_se_puede_omitir_y_el_turno_en_curso_no_cuenta(self):
        self.proyecto()
        self.agente.chat('primera petición')
        self.assertIn('primera petición', self.ficha())
        self.assertNotIn('LO ÚLTIMO QUE PIDIÓ', self.ficha(con_peticiones=False))
        with self.agente.store() as store:
            turno = store.db.execute("SELECT id FROM esta_ventana WHERE role='user'").fetchone()[0]
        self.assertNotIn('primera petición', self.ficha(salvo=turno))

    def test_tiene_tope_por_mucho_que_se_haya_hecho(self):
        self.proyecto()
        with self.agente.store() as store:
            for i in range(60):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                                 ('m%d' % i, '2026-11-13T16:%02d:00+00:00' % i, 'user', 'petición %d ' % i + 'x' * 400, ''))
            store.db.commit()
        self.assertLessEqual(len(self.ficha()), projects.MAX_FICHA + 1)

    def test_no_cuenta_nada_de_otro_proyecto(self):
        self.proyecto('uno')
        self.agente.chat('la clave del uno es azafrán')
        self.proyecto('dos')
        self.assertNotIn('azafrán', self.ficha())
        self.assertIn('recién empezado', self.ficha())


class InyeccionTest(Base):
    """HexOS pone la ficha delante al reconstruir el contexto; el modelo no la pide."""

    def setUp(self):
        super().setUp()
        self.runtime = Nativo()
        self.agente = Agent(self.casa / 'hexos-nativo', self.runtime)
        self.agente.set_window('agente')

    def test_entra_al_empezar_y_no_se_repite_mientras_el_contexto_sigue_vivo(self):
        self.agente.create_project('Motor CUDA')
        self.agente.chat('¿tienes una carpeta de proyecto?')
        self.assertIn('PROYECTO ACTIVO', self.runtime.vistos[-1])
        self.assertIn('motor-cuda', self.runtime.vistos[-1])
        self.agente.chat('sigue')
        self.assertNotIn('PROYECTO ACTIVO', self.runtime.vistos[-1])       # el prefijo ya la lleva

    def test_tras_limpiar_el_contexto_vuelve_con_lo_ultimo_pedido(self):
        self.agente.create_project('Motor CUDA')
        self.agente.chat('optimiza el kernel de atención')
        self.agente.clear_context()
        self.agente.chat('¿por dónde íbamos?')
        visto = self.runtime.vistos[-1]
        self.assertIn('PROYECTO ACTIVO', visto)
        self.assertIn('LO ÚLTIMO QUE PIDIÓ LA PERSONA AQUÍ', visto)
        self.assertIn('optimiza el kernel de atención', visto)

    def test_al_volver_a_un_proyecto_entra_la_suya(self):
        self.agente.create_project('uno')
        self.agente.chat('hola uno')
        self.agente.create_project('dos')
        self.agente.chat('hola dos')
        self.assertIn('«dos»', self.runtime.vistos[-1])
        self.assertNotIn('«uno»', self.runtime.vistos[-1])
        self.agente.set_project('uno')
        self.agente.chat('sigo')
        self.assertIn('«uno»', self.runtime.vistos[-1])

    def test_sin_proyecto_y_en_el_chat_no_hay_ficha(self):
        self.agente.chat('sin proyecto')
        self.assertNotIn('PROYECTO ACTIVO', self.runtime.vistos[-1])
        self.agente.create_project('uno')
        self.agente.set_window('chat')
        self.agente.chat('en el chat')
        self.assertNotIn('PROYECTO ACTIVO', self.runtime.vistos[-1])


class ServidorTest(Base):
    """Las rutas que usará la interfaz, por HTTP de verdad."""

    def setUp(self):
        super().setUp()
        from http.server import ThreadingHTTPServer
        import threading
        from hexos.agent.chat_backend.server import make_handler
        ui = self.casa / 'ui.html'
        ui.write_text('x')
        self.servidor = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.agente, lambda: {}, set(), ui))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.servidor.server_address[1]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        super().tearDown()

    def pedir(self, ruta, cuerpo=None):
        import urllib.error
        import urllib.request
        datos = None if cuerpo is None else json.dumps(cuerpo).encode()
        peticion = urllib.request.Request(self.url + ruta, data=datos, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(peticion, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_crear_listar_cambiar_y_salir(self):
        self.assertEqual(self.pedir('/api/projects'), (200, dict(active=None, projects=[])))
        codigo, creado = self.pedir('/api/projects', dict(name='Motor CUDA'))
        self.assertEqual((codigo, creado['active']), (200, 'motor-cuda'))
        self.pedir('/api/projects', dict(name='Películas'))
        codigo, lista = self.pedir('/api/projects')
        self.assertEqual((lista['active'], [p['id'] for p in lista['projects']]), ('peliculas', ['peliculas', 'motor-cuda']))
        self.assertEqual(self.pedir('/api/project', dict(id='motor-cuda'))[1]['active'], 'motor-cuda')
        self.assertEqual(self.pedir('/api/status')[1]['project'], 'motor-cuda')
        self.assertEqual(self.pedir('/api/project', dict(id=None))[1]['active'], None)
        self.assertIsNone(self.pedir('/api/status')[1]['project'])

    def test_lo_mal_pedido_se_rechaza_sin_crear_nada(self):
        for ruta, cuerpo in (('/api/projects', dict(nombre='x')), ('/api/projects', dict(name='x', otra=1)),
                             ('/api/projects', dict(name='x', folder='/etc')), ('/api/project', dict(id='fantasma')),
                             ('/api/project', {})):
            with self.subTest(ruta=ruta, cuerpo=cuerpo):
                self.assertGreaterEqual(self.pedir(ruta, cuerpo)[0], 400)
        self.assertEqual(self.pedir('/api/projects')[1]['projects'], [])


class AlmacenAntiguoTest(unittest.TestCase):
    def test_un_almacen_de_antes_de_los_proyectos_se_actualiza_sin_perder_mensajes(self):
        with tempfile.TemporaryDirectory(prefix='hexos-viejo-') as tmp:
            Agent(tmp, Runtime()).chat('mensaje viejo')
            # La regla de antes: solo la ventana, sin proyecto.
            db = sqlite3.connect(str(Path(tmp) / 'work.sqlite'))
            db.executescript('DROP TRIGGER conversation_a_su_ventana; DROP VIEW esta_ventana;')
            db.executescript((persistence.POR_VENTANA).replace(persistence.ETIQUETA_ACTUAL, persistence.VENTANA_ACTUAL))
            db.close()
            agente = Agent(tmp, Runtime())
            with agente.store() as store:
                regla = store.db.execute("SELECT sql FROM sqlite_master WHERE name='conversation_a_su_ventana'").fetchone()[0]
                self.assertIn("key='project'", regla)
                self.assertEqual([m['text'] for m in history_page(store)['messages'] if m['role'] == 'user'], ['mensaje viejo'])


if __name__ == '__main__':
    unittest.main()
