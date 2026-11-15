"""Ejecutar dentro del proyecto: en una jaula, sin red y sin salir de la carpeta."""
import json
import os
import shutil
import subprocess
import unittest
import unittest.mock
from pathlib import Path

from hexos.agent import catalog, project_files, project_run
from tools.project_files_test import Base

CON_JAULA = bool(shutil.which('bwrap'))


class Ejecutar(Base):
    def correr(self, *orden, **mas):
        with self.agente.store() as store:
            return project_files.dispatch(store, 'project.run', dict(command=list(orden), **mas))


@unittest.skipUnless(CON_JAULA, 'sin bubblewrap no hay jaula que probar')
class JaulaTest(Ejecutar):
    def setUp(self):
        super().setUp()
        # La carpeta personal de la prueba es temporal; la jaula tapa la de verdad.
        self.casa_real = Path(os.path.expanduser('~'))

    def test_ejecuta_y_devuelve_salida_y_codigo(self):
        self.escribir('suma.py', 'print(2 + 3)\n')
        r = self.correr('python3', 'suma.py')
        self.assertEqual((r['output'].strip(), r['exit_code'], r['ok']), ('5', 0, True))
        self.escribir('mal.py', 'import sys\nprint("antes")\nsys.exit(3)\n')
        r = self.correr('python3', 'mal.py')
        self.assertEqual((r['exit_code'], r['ok'], 'antes' in r['output']), (3, False, True))

    def test_sin_red_y_sin_escribir_fuera_del_proyecto(self):
        self.escribir('fuga.py', '\n'.join((
            'import os, socket',
            'try:',
            '    socket.create_connection(("1.1.1.1", 53), 2); print("RED SI")',
            'except OSError: print("red no")',
            'for ruta in ("/usr/fuga-hexos", "/etc/fuga-hexos"):',
            '    try: open(ruta, "w"); print("ESCRIBE", ruta)',
            '    except OSError: print("no escribe", ruta)',
            'open(os.path.expanduser("~/fuga-hexos.txt"), "w").write("x")',
            'print("ssh", os.path.exists(os.path.expanduser("~/.ssh")))',
            'print("zocalos", os.listdir("/run"), os.path.exists("/run/user/%d/bus" % os.getuid()))',
            'open("dentro.txt", "w").write("ok")', '')))
        salida = self.correr('python3', 'fuga.py')['output']
        self.assertIn('red no', salida)
        self.assertNotIn('ESCRIBE', salida)
        self.assertIn('ssh False', salida)
        self.assertIn('zocalos [] False', salida)
        self.assertEqual((self.repo / 'dentro.txt').read_text(), 'ok')
        self.assertFalse((self.casa_real / 'fuga-hexos.txt').exists())      # la carpeta personal era de usar y tirar
        self.assertFalse((self.casa / 'fuga-hexos.txt').exists())

    def test_un_programa_que_no_acaba_se_para_y_se_dice(self):
        self.escribir('eterno.py', 'import time\nprint("empiezo", flush=True)\ntime.sleep(60)\n')
        r = self.correr('python3', 'eterno.py', timeout=2)
        self.assertEqual((r['exit_code'], r['ok'], 'timed_out' in r), (None, False, True))
        # Seguir vivo sin errores es «arranca», no un fallo; con errores a la vista, se dice.
        self.assertIn('eso es que arranca bien', r['timed_out'])
        self.escribir('roto.py', 'import time\nprint("Traceback (most recent call last):", flush=True)\ntime.sleep(60)\n')
        self.assertIn('hay errores', self.correr('python3', 'roto.py', timeout=2)['timed_out'])

    def test_una_salida_enorme_se_recorta(self):
        self.escribir('ruido.py', 'print("principio")\nprint("x" * 40000)\nprint("final")\n')
        r = self.correr('python3', 'ruido.py')
        self.assertLess(len(r['output']), 7000)
        self.assertTrue(r['output'].startswith('principio') and r['output'].rstrip().endswith('final'))
        self.assertIn('truncated', r)

    def test_hexos_apunta_en_la_memoria_que_se_ejecuto_y_como_acabo(self):
        self.escribir('ok.py', 'print(1)\n')
        self.correr('python3', 'ok.py')
        self.correr('python3', 'ok.py')
        apuntes = json.loads((self.repo / '.helios' / 'proyecto.json').read_text())['ejecuciones']
        self.assertEqual([a['texto'] for a in apuntes], ['python3 ok.py → bien'])

    def test_un_ejecutable_del_proyecto_si_y_uno_de_fuera_no(self):
        self.escribir('hola.sh', '#!/bin/sh\necho hola desde el proyecto\n')
        os.chmod(self.repo / 'hola.sh', 0o755)
        self.assertIn('hola desde el proyecto', self.correr('./hola.sh')['output'])
        with self.assertRaisesRegex(ValueError, 'fuera de la carpeta'):
            self.correr('/bin/ls')


@unittest.skipUnless(CON_JAULA and shutil.which('Xvfb'), 'sin Xvfb no hay pantalla virtual que probar')
class PantallaTest(Ejecutar):
    def test_una_ventana_de_tkinter_se_crea_y_se_mide_sin_pantalla_de_verdad(self):
        self.escribir('ventana.py', '\n'.join((
            'import tkinter as tk',
            'r = tk.Tk(); r.geometry("300x200"); b = tk.Button(r, text="Hola"); b.pack(); r.update()',
            'print("ventana", r.winfo_width(), r.winfo_height(), "boton", b.winfo_height() > 5)',
            'r.destroy()', '')))
        r = self.correr('python3', 'ventana.py')
        self.assertEqual((r['exit_code'], r['output'].strip()), (0, 'ventana 300 200 boton True'))

    def test_el_codigo_de_salida_del_programa_se_conserva(self):
        self.escribir('mal.py', 'import sys\nsys.exit(3)\n')
        self.assertEqual(self.correr('python3', 'mal.py')['exit_code'], 3)


class LimitesTest(Ejecutar):
    def test_solo_programas_conocidos_y_sin_shell(self):
        for orden, dice in ((('bash', '-c', 'ls'), 'no se puede ejecutar'), (('rm', '-rf', '.'), 'no se puede ejecutar'),
                            (('curl', 'http://x'), 'no se puede ejecutar'), (('sudo', 'apt'), 'no se puede ejecutar'),
                            (('pip', 'install', 'PyQt6'), 'system_package_plan'), (('README.md',), 'no se puede ejecutar'),
                            (('./README.md',), 'no es un ejecutable')):
            with self.subTest(orden=orden), self.assertRaisesRegex(ValueError, dice):
                self.correr(*orden)
        with self.assertRaisesRegex(ValueError, 'lista de argumentos'):
            with self.agente.store() as store:
                project_files.dispatch(store, 'project.run', dict(command='python3 -m unittest'))
        with self.assertRaisesRegex(ValueError, 'timeout'):
            self.correr('python3', '-V', timeout=9999)

    def test_sin_bubblewrap_no_se_ejecuta_nada(self):
        lanzadas = []
        original = shutil.which
        with unittest.mock.patch.object(project_run.shutil, 'which', lambda n: None if n == 'bwrap' else original(n)):
            with self.agente.store() as store, self.assertRaisesRegex(ValueError, 'bubblewrap'):
                project_run.run(store, ['python3', '-V'], lanzar=lambda *a, **k: lanzadas.append(a))
        self.assertEqual(lanzadas, [])

    def test_sin_xvfb_la_orden_va_tal_cual(self):
        original = shutil.which
        with unittest.mock.patch.object(project_run.shutil, 'which', lambda n: None if n == 'Xvfb' else original(n)):
            self.assertEqual(project_run.con_pantalla(['/usr/bin/python3', 'a.py']), ['/usr/bin/python3', 'a.py'])
        with unittest.mock.patch.object(project_run.shutil, 'which', lambda n: '/usr/bin/' + n):
            orden = project_run.con_pantalla(['/usr/bin/python3', 'a.py'])
        self.assertEqual((orden[0], orden[3], orden[-2:]), ('/usr/bin/python3', '/usr/bin/Xvfb', ['/usr/bin/python3', 'a.py']))

    def test_la_jaula_va_sin_red_y_con_la_casa_tapada(self):
        orden = project_run.jaula(self.repo)
        if orden is None:
            self.skipTest('sin bubblewrap')
        self.assertIn('--unshare-net', orden)
        self.assertEqual(orden[orden.index('--bind') + 1], str(self.repo))
        self.assertLess(orden.index('--tmpfs'), orden.index('--bind'))
        self.assertNotIn('SSH_AUTH_SOCK', project_run._entorno())


class CatalogoTest(unittest.TestCase):
    def test_va_en_el_grupo_del_proyecto_y_no_en_el_chat(self):
        self.assertIn('project.run', catalog.tools_for(['proyecto'], 'agente'))
        self.assertNotIn('project.run', catalog.tools_for(list(catalog.groups_in('chat')), 'chat'))
        catalog.validate('project.run', dict(command=['python3', '-m', 'unittest']))


if __name__ == '__main__':
    unittest.main()
