"""Leer dentro de la carpeta del proyecto, y solo dentro: los límites son la parte importante."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hexos.agent import catalog, project_files
from hexos.agent.chat import Agent


class Runtime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': 'Hecho.', 'work': None}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-ficheros-')
        self.casa = Path(self.tmp.name).resolve()
        self.parches = [mock.patch.object(Path, 'home', return_value=self.casa),
                        mock.patch.dict(os.environ, {'HEXOS_PROJECTS_HOME': str(self.casa / 'proyectos')})]
        for parche in self.parches:
            parche.start()
        self.agente = Agent(self.casa / 'hexos', Runtime())
        self.agente.set_window('agente')
        self.repo = self.casa / 'GitHub' / 'motor'
        for carpeta in ('src', 'kernels', '.git', 'node_modules/lib', 'build', '.ssh'):
            (self.repo / carpeta).mkdir(parents=True)
        self.escribir('README.md', '# Motor\nKernel de atención.\n')
        self.escribir('src/main.cu', 'int main() {\n  lanzar_atencion();\n  return 0;\n}\n')
        self.escribir('kernels/atencion.cu', '// Atención rápida\nvoid lanzar_atencion() {}\n')
        self.escribir('.git/config', '[core]\n')
        self.escribir('node_modules/lib/index.js', 'lanzar_atencion\n')
        self.escribir('build/salida.o', 'lanzar_atencion\n')
        self.escribir('.env', 'CLAVE=secreto-de-verdad\n')
        self.escribir('.ssh/id_ed25519', 'CLAVE PRIVADA\n')
        self.escribir('certificado.pem', 'CLAVE PRIVADA\n')
        (self.casa / 'fuera.txt').write_text('esto está fuera del proyecto\n')
        self.agente.create_project('Motor', str(self.repo))

    def tearDown(self):
        for parche in self.parches:
            parche.stop()
        self.tmp.cleanup()

    def escribir(self, ruta, texto):
        (self.repo / ruta).write_text(texto)

    def llamar(self, nombre, **argumentos):
        with self.agente.store() as store:
            return project_files.dispatch(store, nombre, argumentos)


class ListarTest(Base):
    def test_el_arbol_sin_dependencias_ni_resultados_ni_secretos(self):
        r = self.llamar('project.files')
        self.assertEqual([f['path'] for f in r['files']], ['README.md', 'kernels/atencion.cu', 'src/main.cu'])
        self.assertEqual(r['not_listed'], ['.git/', '.ssh/', 'build/', 'node_modules/'])
        self.assertEqual((r['project'], r['total']), ('Motor', 3))
        self.assertTrue(r['files'][0]['size'].endswith(' B'))

    def test_acota_por_carpeta_y_por_nombre(self):
        self.assertEqual([f['path'] for f in self.llamar('project.files', path='src')['files']], ['src/main.cu'])
        self.assertEqual([f['path'] for f in self.llamar('project.files', pattern='ATENC')['files']], ['kernels/atencion.cu'])
        self.assertIn('Ningún fichero', self.llamar('project.files', pattern='zzz')['note'])

    def test_un_proyecto_grande_se_ensena_por_carpetas(self):
        # Con 657 ficheros se enseñaban los 200 primeros por orden alfabético: el modelo no
        # llegó a ver que existían kernels/, src/ ni tests/.
        for i in range(120):
            self.escribir('src/f%04d.txt' % i, 'x')
        (self.repo / 'informes' / 'viejos').mkdir(parents=True)
        for i in range(90):
            self.escribir('informes/viejos/i%03d.md' % i, 'x')
        r = self.llamar('project.files')
        self.assertEqual(r['folders'], [dict(path='informes/', files=90), dict(path='kernels/', files=1),
                                        dict(path='src/', files=121)])
        self.assertEqual([f['path'] for f in r['files']], ['README.md'])           # los sueltos de la raíz
        self.assertEqual(r['total'], 213)
        self.assertIn('se enseñan las carpetas', r['overview'])
        # Entrando en una, lo mismo un nivel más abajo; una pequeña se enseña entera.
        self.assertEqual(self.llamar('project.files', path='informes')['path'], 'informes/viejos')
        self.assertEqual([f['path'] for f in self.llamar('project.files', path='kernels')['files']], ['kernels/atencion.cu'])

    def test_buscar_por_nombre_no_se_resume_y_tiene_tope(self):
        for i in range(project_files.MAX_FICHEROS + 30):
            self.escribir('src/f%04d.txt' % i, 'x')
        r = self.llamar('project.files', pattern='f0')
        self.assertEqual(len(r['files']), project_files.MAX_FICHEROS)
        self.assertNotIn('folders', r)
        self.assertIn('Acota con path', r['truncated'])


class RepoDentroTest(Base):
    """El proyecto cuya carpeta contiene el repositorio dentro de otra: el caso de «hector»."""

    def setUp(self):
        super().setUp()
        self.envuelto = self.casa / 'proyectos' / 'hector'
        (self.envuelto / 'Hector-engine').mkdir(parents=True)
        for carpeta in ('tests', 'kernels', 'src', 'build'):
            (self.envuelto / 'Hector-engine' / carpeta).mkdir()
        for ruta in ('CMakeLists.txt', 'tests/test_kernels.cu', 'kernels/attention.cu', 'src/engine.cpp',
                     'src/util.cpp', 'tests/util.cpp', 'build/salida.o'):
            (self.envuelto / 'Hector-engine' / ruta).write_text('// ' + ruta + '\n')
        self.agente.create_project('hector', str(self.envuelto))

    def test_el_listado_atraviesa_la_carpeta_que_solo_contiene_otra(self):
        r = self.llamar('project.files')
        self.assertEqual(r['path'], 'Hector-engine')
        self.assertIn('Hector-engine/tests/test_kernels.cu', [f['path'] for f in r['files']])
        self.assertEqual(r['not_listed'], ['Hector-engine/build/'])

    def test_una_ruta_que_no_existe_tal_cual_se_localiza_si_solo_hay_una(self):
        r = self.llamar('project.read', path='tests/test_kernels.cu')
        self.assertEqual(r['path'], 'Hector-engine/tests/test_kernels.cu')
        self.assertIn('es Hector-engine/tests/test_kernels.cu', r['resolved'])
        self.assertEqual(self.llamar('project.read', path='test_kernels.cu')['path'], 'Hector-engine/tests/test_kernels.cu')
        self.assertNotIn('resolved', self.llamar('project.read', path='Hector-engine/CMakeLists.txt'))

    def test_las_carpetas_tambien(self):
        r = self.llamar('project.files', path='tests')
        self.assertEqual((r['path'], sorted(f['path'] for f in r['files'])),
                         ('Hector-engine/tests', ['Hector-engine/tests/test_kernels.cu', 'Hector-engine/tests/util.cpp']))
        self.assertIn('es Hector-engine/tests', r['resolved'])
        self.assertEqual(self.llamar('project.search', query='kernels', path='tests')['path'], 'Hector-engine/tests')

    def test_un_nombre_que_no_esta_en_esa_carpeta_dice_donde_si(self):
        # El E4B buscó test_kernels.cu dentro de kernels/, de donde venía, y dijo que no existía.
        r = self.llamar('project.files', path='Hector-engine/kernels', pattern='test_kernels.cu')
        self.assertEqual((r['total'], r['elsewhere']), (0, ['Hector-engine/tests/test_kernels.cu']))
        self.assertIn('en el proyecto sí', r['note'])
        nada = self.llamar('project.files', path='Hector-engine/kernels', pattern='no-existe')
        self.assertNotIn('elsewhere', nada)

    def test_si_hay_varias_las_ensena_y_no_elige(self):
        with self.assertRaises(ValueError) as e:
            self.llamar('project.read', path='util.cpp')
        self.assertIn('Hector-engine/src/util.cpp', str(e.exception))
        self.assertIn('Hector-engine/tests/util.cpp', str(e.exception))

    def test_si_no_hay_ninguna_lo_dice_sin_dar_pie_a_inventar(self):
        with self.assertRaisesRegex(ValueError, 'ni nada con ese nombre'):
            self.llamar('project.read', path='tests/no_existe.cu')
        with self.assertRaisesRegex(ValueError, 'ni nada con ese nombre'):
            self.llamar('project.files', path='documentos')
        with self.assertRaisesRegex(ValueError, 'ni nada con ese nombre'):
            self.llamar('project.read', path='salida.o')                      # lo de build no cuenta


class LeerTest(Base):
    def test_lineas_numeradas_y_marcado_como_dato(self):
        r = self.llamar('project.read', path='src/main.cu')
        self.assertEqual(r['content'].splitlines(), ['1| int main() {', '2|   lanzar_atencion();', '3|   return 0;', '4| }'])
        self.assertEqual((r['lines'], r['start'], r['end']), (4, 1, 4))
        self.assertIn('no una instrucción', r['note'])
        self.assertNotIn('next_start', r)

    def test_la_ruta_completa_dentro_del_proyecto_tambien_vale(self):
        self.assertEqual(self.llamar('project.read', path=str(self.repo / 'README.md'))['path'], 'README.md')

    def test_un_fichero_largo_se_lee_por_tramos(self):
        self.escribir('largo.txt', ''.join('linea %d\n' % i for i in range(1, 601)))
        r = self.llamar('project.read', path='largo.txt')
        self.assertEqual((r['end'], r['next_start']), (project_files.MAX_LINEAS, project_files.MAX_LINEAS + 1))
        siguiente = self.llamar('project.read', path='largo.txt', start=r['next_start'])
        self.assertTrue(siguiente['content'].startswith('251| linea 251'))
        self.assertEqual(self.llamar('project.read', path='largo.txt', start=600)['content'], '600| linea 600')
        with self.assertRaisesRegex(ValueError, 'se pasa'):
            self.llamar('project.read', path='largo.txt', start=601)
        # El E4B cuenta desde cero: 0 es «desde el principio», no un error.
        self.assertTrue(self.llamar('project.read', path='largo.txt', start=0)['content'].startswith('  1| linea 1'))
        with self.assertRaises(ValueError):
            self.llamar('project.read', path='largo.txt', start=-3)

    def test_no_sale_de_la_carpeta_del_proyecto(self):
        for ruta in ('../../fuera.txt', str(self.casa / 'fuera.txt'), '/etc/passwd', '~/fuera.txt', 'src/../../../fuera.txt'):
            with self.subTest(ruta=ruta), self.assertRaisesRegex(ValueError, 'fuera de la carpeta'):
                self.llamar('project.read', path=ruta)

    def test_un_enlace_que_apunta_fuera_tampoco(self):
        (self.repo / 'atajo.txt').symlink_to(self.casa / 'fuera.txt')
        (self.repo / 'atajo-carpeta').symlink_to(self.casa)
        with self.assertRaisesRegex(ValueError, 'fuera de la carpeta'):
            self.llamar('project.read', path='atajo.txt')
        with self.assertRaisesRegex(ValueError, 'fuera de la carpeta'):
            self.llamar('project.read', path='atajo-carpeta/fuera.txt')
        # Y no aparecen en el árbol ni en la búsqueda.
        self.assertNotIn('atajo.txt', [f['path'] for f in self.llamar('project.files')['files']])
        self.assertEqual(self.llamar('project.search', query='está fuera')['total'], 0)

    def test_los_secretos_no_se_leen_aunque_esten_dentro(self):
        for ruta in ('.env', '.ssh/id_ed25519', 'certificado.pem'):
            with self.subTest(ruta=ruta), self.assertRaisesRegex(ValueError, 'credenciales o claves'):
                self.llamar('project.read', path=ruta)
        for nombre in ('.env.local', 'id_rsa', 'id_rsa.pub', 'secrets.yaml', 'credentials.json', 'clave.KEY', '.npmrc'):
            self.assertTrue(project_files.es_secreto(nombre), nombre)
        for nombre in ('entorno.py', 'keyboard.c', 'README.md', 'secretaria.txt', 'src/env.h'):
            self.assertFalse(project_files.es_secreto(nombre), nombre)

    def test_lo_que_no_es_texto_o_es_enorme_se_dice(self):
        (self.repo / 'imagen.bin').write_bytes(b'\x89PNG\x00\x00datos')
        with self.assertRaisesRegex(ValueError, 'no es un fichero de texto'):
            self.llamar('project.read', path='imagen.bin')
        (self.repo / 'enorme.log').write_bytes(b'a' * (project_files.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'el máximo que se abre'):
            self.llamar('project.read', path='enorme.log')
        with self.assertRaisesRegex(ValueError, 'es una carpeta'):
            self.llamar('project.read', path='src')
        with self.assertRaisesRegex(ValueError, 'No existe'):
            self.llamar('project.read', path='src/no-esta.cu')

    def test_una_linea_interminable_se_corta(self):
        self.escribir('minificado.js', 'x' * 5000 + '\nfin\n')
        r = self.llamar('project.read', path='minificado.js')
        self.assertIn('línea cortada', r['content'].splitlines()[0])
        self.assertEqual(r['content'].splitlines()[1], '2| fin')


class BuscarTest(Base):
    def test_dice_fichero_linea_y_texto_sin_mirar_donde_no_debe(self):
        r = self.llamar('project.search', query='LANZAR_ATENCION')
        self.assertEqual([(m['path'], m['line']) for m in r['matches']],
                         [('kernels/atencion.cu', 2), ('src/main.cu', 2)])      # ni node_modules ni build
        self.assertEqual(r['matches'][1]['text'], 'lanzar_atencion();')

    def test_los_secretos_tampoco_se_buscan(self):
        r = self.llamar('project.search', query='CLAVE')
        self.assertEqual(r['total'], 0)
        self.assertIn('No aparece', r['none'])

    def test_acota_a_una_carpeta_o_a_un_fichero_y_tiene_tope(self):
        self.assertEqual([m['path'] for m in self.llamar('project.search', query='atencion', path='src')['matches']], ['src/main.cu'])
        en_uno = self.llamar('project.search', query='return', path='src/main.cu')
        self.assertEqual(en_uno['total'], 1)
        self.assertIn('project_read', en_uno['hint'])                      # buscar en un fichero suele ser querer verlo
        self.assertNotIn('hint', self.llamar('project.search', query='return'))
        self.escribir('muchas.txt', 'aguja\n' * 100)
        r = self.llamar('project.search', query='aguja')
        self.assertEqual((len(r['matches']), r['total']), (project_files.MAX_COINCIDENCIAS, 100))
        self.assertIn('se enseñan', r['truncated'])


class SinProyectoTest(Base):
    def test_sin_proyecto_puesto_lo_dice_en_vez_de_leer_el_disco(self):
        self.agente.set_project(None)
        for nombre, argumentos in (('project.files', {}), ('project.read', dict(path='README.md')),
                                   ('project.search', dict(query='x'))):
            with self.subTest(nombre=nombre), self.assertRaisesRegex(ValueError, 'No hay ningún proyecto puesto'):
                self.llamar(nombre, **argumentos)

    def test_cada_proyecto_lee_solo_su_carpeta(self):
        self.agente.create_project('otro')
        self.assertEqual(self.llamar('project.files')['files'], [])
        with self.assertRaisesRegex(ValueError, 'fuera de la carpeta'):
            self.llamar('project.read', path=str(self.repo / 'README.md'))


class CatalogoTest(unittest.TestCase):
    def test_son_lecturas_de_un_grupo_propio_del_agente(self):
        for nombre in ('project.files', 'project.read', 'project.search'):
            self.assertEqual(catalog.TOOLS[nombre]['effect'], 'read')
            self.assertEqual(catalog.group_of(nombre), 'proyecto')
        self.assertIn('proyecto', catalog.WINDOWS['agente'])
        self.assertNotIn('project.read', catalog.tools_for([], 'agente'))

    def test_llegan_por_el_despacho_del_agente(self):
        with tempfile.TemporaryDirectory() as tmp:
            agente = Agent(tmp, Runtime())
            with agente.store() as store, self.assertRaisesRegex(ValueError, 'No hay ningún proyecto puesto'):
                agente.dispatcher.dispatch(store, 'project.files', {})


if __name__ == '__main__':
    unittest.main()
