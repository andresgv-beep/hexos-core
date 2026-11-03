"""Instalar y quitar programas con plan, aprobación y comprobación (docs/PAQUETES_CON_APROBACION.md).

Sin tocar el sistema: las lecturas y el ayudante se simulan.
"""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog, system_packages
from hexos.agent.chat import Agent

AYUDANTE = SourceFileLoader('hexos_paquetes', str(Path(__file__).resolve().parents[1] / 'runtime' / 'hexos-paquetes')).load_module()


def sistema(instalados=(), simulacion='', flathub=(), snaps=(), flatpaks=(), snaps_instalados=()):
    """Un PC de mentira: qué responde cada lectura. `instalados` son paquetes de apt."""
    def runner(orden):
        if orden[0] == 'dpkg-query':
            return (0, 'install ok installed') if orden[-1] in instalados else (1, 'no packages found')
        if orden[:2] == ['apt-get', '-s']:
            return (100, 'E: Unable to locate package ' + orden[-1]) if simulacion is None else (0, simulacion)
        if orden[:2] == ['flatpak', 'info']:
            return (0, 'ok') if orden[-1] in flatpaks else (1, 'not installed')
        if orden[:2] == ['flatpak', 'remote-info']:
            return (0, 'ok') if orden[-1] in flathub else (1, 'not found')
        if orden[:2] == ['snap', 'list']:
            return (0, 'ok') if orden[-1] in snaps_instalados else (1, 'no snap')
        if orden[:2] == ['snap', 'info']:
            return (0, 'ok') if orden[-1] in snaps else (1, 'no snap')
        raise AssertionError('lectura inesperada: ' + ' '.join(orden))
    return runner


class PlanTest(unittest.TestCase):
    def test_quitar_deduce_el_gestor_y_simula_lo_que_arrastra(self):
        pc = sistema(instalados={'nomachine'}, simulacion='Remv nomachine [9.1.24]\nRemv nxplayer [9]\n')
        plan = system_packages.plan('remove', 'nomachine', runner=pc)
        self.assertEqual((plan['manager'], plan['affects'], plan['affects_count']), ('apt', ['nomachine', 'nxplayer'], 2))
        self.assertIn('Quitar nomachine con apt', plan['summary'])

    def test_lo_protegido_se_rechaza_ya_al_planificar(self):
        with self.assertRaises(ValueError) as e:
            system_packages.plan('remove', 'sudo', runner=sistema(instalados={'sudo'}, simulacion='Remv sudo [1]\n'))
        self.assertIn('protegido', str(e.exception))
        arrastra = 'Remv libfoo [1]\nRemv gdm3 [46]\n'
        with self.assertRaises(ValueError) as e:
            system_packages.plan('remove', 'libfoo', runner=sistema(instalados={'libfoo'}, simulacion=arrastra))
        self.assertIn('gdm3', str(e.exception))

    def test_quitar_lo_que_no_esta_lo_dice_sin_planificar(self):
        with self.assertRaises(ValueError) as e:
            system_packages.plan('remove', 'gimp', runner=sistema())
        self.assertIn('no está instalado', str(e.exception))

    def test_instalar_exige_el_gestor_y_no_lo_adivina(self):
        with self.assertRaises(ValueError) as e:
            system_packages.plan('install', 'gimp', runner=sistema())
        self.assertIn('indica manager', str(e.exception))

    def test_instalar_lo_que_ya_esta_no_planifica(self):
        with self.assertRaises(ValueError) as e:
            system_packages.plan('install', 'gimp', 'apt', runner=sistema(instalados={'gimp'}))
        self.assertIn('ya está instalado', str(e.exception))

    def test_un_paquete_que_apt_no_encuentra_no_llega_a_plan(self):
        with self.assertRaises(ValueError) as e:
            system_packages.plan('install', 'noexiste', 'apt', runner=sistema(simulacion=None))
        self.assertIn('Unable to locate', str(e.exception))

    def test_flatpak_y_snap_comprueban_que_existe_en_su_origen(self):
        plan = system_packages.plan('install', 'org.gimp.GIMP', 'flatpak', runner=sistema(flathub={'org.gimp.GIMP'}))
        self.assertEqual(plan['affects'], ['org.gimp.GIMP'])
        with self.assertRaises(ValueError):
            system_packages.plan('install', 'nada', 'snap', runner=sistema())

    def test_nombres_con_opciones_o_rutas_se_rechazan(self):
        for nombre in ('-y', 'gimp;rm', '../x', 'Gimp Editor', ''):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                system_packages.plan('install', nombre, 'apt', runner=sistema())


class AplicarTest(unittest.TestCase):
    PLAN = dict(plan_id='p1', manager='apt', action='remove', package='nomachine', summary='Quitar nomachine con apt')

    def test_hecho_y_comprobado_aparte(self):
        r = system_packages.apply(self.PLAN, ayudante=lambda *a: dict(ok=True, salida='Removing nomachine'),
                                  runner=sistema())
        self.assertTrue(r['executed'] and r['verified'])
        self.assertIn('no instalado', r['check'])

    def test_si_dice_que_si_pero_sigue_instalado_no_se_da_por_hecho(self):
        r = system_packages.apply(self.PLAN, ayudante=lambda *a: dict(ok=True), runner=sistema(instalados={'nomachine'}))
        self.assertTrue(r['executed'])
        self.assertFalse(r['verified'])

    def test_un_rechazo_del_ayudante_llega_con_su_motivo(self):
        r = system_packages.apply(self.PLAN, ayudante=lambda *a: dict(ok=False, rechazado='protegido'),
                                  runner=sistema(instalados={'nomachine'}))
        self.assertFalse(r['executed'])
        self.assertEqual(r['refused'], 'protegido')


class AyudanteTest(unittest.TestCase):
    """runtime/hexos-paquetes: la puerta con root se defiende sola."""

    def test_lista_cerrada(self):
        for args in (['apt', 'instalar'], ['dnf', 'instalar', 'x'], ['apt', 'purgar', 'x'], ['apt', 'instalar', '-y']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                AYUDANTE.principal(args)

    def test_protegidos_no_se_quitan(self):
        for nombre in ('sudo', 'tailscale', 'linux-image-6.8.0-45-generic', 'nvidia-driver-570', 'python3'):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError) as e:
                AYUDANTE.principal(['apt', 'quitar', nombre])
            self.assertIn('protegido', str(e.exception))

    def test_una_desinstalacion_que_arrastra_protegidos_se_rechaza_antes(self):
        simulacion = 'Remv libfoo [1]\nRemv gnome-shell [46]\n'
        with patch.object(AYUDANTE, 'correr', return_value=(0, simulacion)), self.assertRaises(ValueError) as e:
            AYUDANTE.principal(['apt', 'quitar', 'libfoo'])
        self.assertIn('gnome-shell', str(e.exception))

    def test_una_desinstalacion_masiva_se_rechaza(self):
        simulacion = ''.join('Remv lib' + str(i) + ' [1]\n' for i in range(20))
        with patch.object(AYUDANTE, 'correr', return_value=(0, simulacion)), self.assertRaises(ValueError) as e:
            AYUDANTE.principal(['apt', 'quitar', 'lib0'])
        self.assertIn('arrastraría 20', str(e.exception))

    def test_ordenes_sin_shell(self):
        self.assertEqual(AYUDANTE.orden_para('flatpak', 'quitar', 'org.gimp.GIMP'),
                         ['flatpak', 'uninstall', '-y', '--noninteractive', '--system', 'org.gimp.GIMP'])
        self.assertEqual(AYUDANTE.orden_para('snap', 'instalar', 'vlc'), ['snap', 'install', 'vlc'])
        self.assertEqual(AYUDANTE.orden_para('apt', 'instalar', 'gimp'), ['apt-get', 'install', '-y', 'gimp'])


class FakeRuntime:
    def call(self, request):
        pass

    def generate(self, messages):
        return {'reply': 'ok', 'work': None}


class AprobacionTest(unittest.TestCase):
    """La ejecución solo llega por la aprobación de la interfaz, del plan pendiente y una vez."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-paquetes-test-')
        self.agent = Agent(self.tmp.name, FakeRuntime())
        self.agent.session.system_request = dict(AplicarTest.PLAN)

    def tearDown(self):
        self.tmp.cleanup()

    def notas(self):
        db = sqlite3.connect(str(Path(self.tmp.name) / 'work.sqlite'))
        try:
            return [fila[0] for fila in db.execute('SELECT text FROM conversation')]
        finally:
            db.close()

    def test_el_modelo_no_tiene_herramienta_para_aplicar(self):
        self.assertEqual([n for n in catalog.model_tools() if n.startswith('system.')], ['system.package_plan'])
        self.assertEqual(catalog.TOOLS['system.package_plan']['effect'], 'read')

    def test_aprobar_ejecuta_comprueba_y_lo_anota(self):
        hecho = dict(plan_id='p1', summary='Quitar nomachine con apt', executed=True, verified=True,
                     refused=None, check='nomachine no instalado según apt')
        r = self.agent.decide_system(dict(plan_id='p1', approve=True), apply=lambda plan: hecho)
        self.assertTrue(r['verified'])
        self.assertIsNone(self.agent.system_request)
        self.assertIn('hecho y comprobado', self.notas()[-1])

    def test_rechazar_no_ejecuta(self):
        llamado = []
        r = self.agent.decide_system(dict(plan_id='p1', approve=False), apply=llamado.append)
        self.assertTrue(r['cancelled'])
        self.assertEqual(llamado, [])
        self.assertIn('rechazó', self.notas()[-1])

    def test_dos_pantallas_aprueban_a_la_vez_y_solo_se_ejecuta_una(self):
        import threading
        llamadas, errores, salida = [], [], threading.Barrier(2)

        def aplicar(plan):
            llamadas.append(plan['plan_id'])
            return dict(plan_id='p1', summary=plan['summary'], executed=True, verified=True, refused=None, check='ok')

        def pantalla():
            salida.wait()
            try:
                self.agent.decide_system(dict(plan_id='p1', approve=True), apply=aplicar)
            except ValueError as e:
                errores.append(str(e))
        hilos = [threading.Thread(target=pantalla) for _ in range(2)]
        for h in hilos: h.start()
        for h in hilos: h.join()
        self.assertEqual(llamadas, ['p1'])
        self.assertEqual(len(errores), 1)
        self.assertIn('otra pantalla', errores[0])

    def test_solo_el_plan_pendiente_y_una_vez(self):
        with self.assertRaises(ValueError):
            self.agent.decide_system(dict(plan_id='otro', approve=True), apply=lambda plan: None)
        self.agent.decide_system(dict(plan_id='p1', approve=False))
        with self.assertRaises(ValueError):
            self.agent.decide_system(dict(plan_id='p1', approve=True), apply=lambda plan: None)


if __name__ == '__main__':
    unittest.main()
