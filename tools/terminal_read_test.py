"""La terminal de lectura enseña la salida real y no puede cambiar nada."""
import unittest

from hexos.agent import terminal_read


class TerminalReadTest(unittest.TestCase):
    def test_ordenes_de_escritura_no_pasan(self):
        for orden in ('apt remove gimp', 'apt-get remove gimp', 'dpkg -r gimp', 'dpkg --purge gimp',
                      'flatpak uninstall x', 'snap remove x', 'rm -rf /', 'sudo ls', 'bash -c ls',
                      'systemctl stop ssh', 'journalctl --vacuum-time=1s', 'apt-mark hold gimp',
                      'cat /etc/shadow', 'python3 -c 1'):
            with self.assertRaises(ValueError, msg=orden):
                terminal_read.trocear(orden)

    def test_tuberias_y_redirecciones_se_rechazan(self):
        for orden in ('dpkg -l | grep gimp', 'ls ; rm x', 'ls > /tmp/x', 'ls && rm x', 'ls $(rm x)'):
            with self.assertRaisesRegex(ValueError, 'tuberías', msg=orden):
                terminal_read.trocear(orden)

    def test_ordenes_de_lectura_pasan(self):
        for orden in ('dpkg -l', 'apt-cache search video', 'apt-mark showhold', 'flatpak list --app',
                      'flatpak list --app --columns=application,name', 'snap list', 'which gimp',
                      'systemctl status ssh --no-pager', 'journalctl -u ssh -n 20 --no-pager'):
            self.assertTrue(terminal_read.trocear(orden))

    def test_el_error_del_programa_llega_tal_cual(self):
        r = terminal_read.read('dpkg -s paquete-que-no-existe', runner=lambda p: (1, "dpkg-query: package not installed"))
        self.assertEqual((r['exit_code'], r['output']), (1, 'dpkg-query: package not installed'))

    def test_filter_acota_sin_tuberia(self):
        r = terminal_read.read('dpkg -l', filter='GIMP', runner=lambda p: (0, 'ii gimp 3\nii vim 9\nii libgimp 3'))
        self.assertEqual(r['output'], 'ii gimp 3\nii libgimp 3')
        self.assertEqual((r['lines'], r['lines_before_filter']), (2, 3))

    def test_salida_larga_se_recorta_y_lo_dice(self):
        r = terminal_read.read('dpkg -l', runner=lambda p: (0, 'x' * 9000))
        self.assertEqual(len(r['output']), terminal_read.MAX_SALIDA)
        self.assertTrue(r['truncated'])

    def test_dice_que_gestores_faltan_por_mirar(self):
        self.assertEqual(terminal_read.sin_mirar(['dpkg -l']), ['flatpak', 'snap'])
        self.assertEqual(terminal_read.sin_mirar(['dpkg -l', 'flatpak list']), ['snap'])
        self.assertEqual(terminal_read.sin_mirar(['snap list', 'flatpak list', 'apt-cache search x']), [])
        self.assertEqual(terminal_read.sin_mirar(['dpkg -l', 'df -h']), [])

    def test_dice_que_ambito_de_servicios_falta(self):
        self.assertEqual(terminal_read.sin_mirar(['systemctl list-units --failed']), ['systemctl --user list-units --failed'])
        self.assertEqual(terminal_read.sin_mirar(['systemctl --user list-units --failed']), ['systemctl list-units --failed'])
        self.assertEqual(terminal_read.sin_mirar(['systemctl --failed', 'systemctl --user --failed']), [])
        self.assertEqual(terminal_read.sin_mirar(['journalctl -u x']), ['journalctl --user -u x'])

    def test_servicio_caido_lleva_a_su_registro(self):
        orden = 'systemctl --user status x.service'
        self.assertEqual(terminal_read.falta_tras([orden], dict(exit_code=3)),
                         ['journalctl --user -u x.service -n 20 --no-pager'])
        self.assertEqual(terminal_read.falta_tras(['systemctl status x.service'], dict(exit_code=3)),
                         ['journalctl -u x.service -n 20 --no-pager'])
        self.assertEqual(terminal_read.falta_tras([orden], dict(exit_code=0)), ['systemctl status x.service'])
        self.assertEqual(terminal_read.falta_tras(['journalctl --user -u x', orden], dict(exit_code=3)), ['systemctl status x.service'])

    def test_este_pc_dice_donde_corre(self):
        pc = terminal_read.este_pc()
        self.assertEqual(pc['se_mira_con'], 'terminal_read')
        self.assertTrue(pc['nombre'] and pc['sistema'])

    def test_filter_no_es_una_opcion(self):
        with self.assertRaisesRegex(ValueError, 'opciones'):
            terminal_read.read('journalctl -u x', filter='-n 20')

    def test_orden_real_del_sistema(self):
        r = terminal_read.read('uname -r')
        self.assertEqual(r['exit_code'], 0)
        self.assertTrue(r['output'].strip())


def equipo(apt='', snap='', flatpak='', dpkg='', sin=()):
    """Un PC de mentira: qué lista cada gestor. `sin` son los que no están instalados."""
    salidas = dict(apt='Listing...\n' + apt, snap=snap, flatpak=flatpak, dpkg=dpkg)
    vistas = []
    def runner(partes):
        vistas.append(' '.join(partes))
        if partes[0] in sin:
            return 127, 'No such file or directory'
        return 0, salidas[partes[0]]
    return runner, vistas


SNAPS = 'Name     Version  Rev  Tracking  Publisher  Notes\nspotify  1.2      99   stable    spotify    -\nvlc      3.0      1    stable    videolan   -'


class BuscarAplicacionTest(unittest.TestCase):
    """Un listado con filter busca en todos los gestores: la cadena la hace la herramienta."""

    def buscar(self, orden, filtro, lanzadores=(), **gestores):
        runner, vistas = equipo(**gestores)
        r = terminal_read.read(orden, filter=filtro, runner=runner,
                               escritorio=lambda texto: [l for l in lanzadores if texto in l])
        return r, vistas

    def test_el_caso_del_10_de_noviembre_se_resuelve_en_una_llamada(self):
        # Preguntó en snap y estaba en apt: antes eran cuatro turnos y una pista de la persona.
        r, vistas = self.buscar('snap list', 'chatgpt', snap=SNAPS,
                                apt='chatgpt/stable,now 26.1103 amd64 [installed]\nvim/stable 9 amd64 [installed]',
                                lanzadores=['/usr/share/applications/chatgpt.desktop'])
        self.assertEqual(r['encontrado_en'], ['apt', 'lanzadores'])
        self.assertEqual(r['tambien_mirado']['apt'], ['chatgpt/stable,now 26.1103 amd64 [installed]'])
        self.assertEqual(r['tambien_mirado']['flatpak'], 'sin coincidencias')
        self.assertEqual(r['lines'], 0)          # en snap, que es donde preguntó, no está
        self.assertEqual(vistas, ['snap list', 'apt list --installed', 'flatpak list'])
        self.assertEqual(terminal_read.falta_tras(['snap list'], r), [])

    def test_donde_esta_va_antes_que_la_salida_del_gestor_preguntado(self):
        r, _ = self.buscar('snap list', 'chatgpt', snap=SNAPS, apt='chatgpt/now 1 amd64 [installed]')
        claves = list(r)
        self.assertLess(claves.index('encontrado_en'), claves.index('lines'))
        self.assertLess(claves.index('encontrado_en'), claves.index('output'))

    def test_encontrada_donde_se_pregunto_tambien_dice_que_no_esta_en_el_resto(self):
        r, _ = self.buscar('snap list', 'spotify', snap=SNAPS, apt='vim/stable 9 amd64 [installed]')
        self.assertEqual(r['encontrado_en'], ['snap'])
        self.assertEqual(r['tambien_mirado'], dict(apt='sin coincidencias', flatpak='sin coincidencias',
                                                   lanzadores='sin coincidencias'))
        self.assertNotIn('sin_rastro', r)

    def test_si_no_esta_en_ningun_sitio_lo_dice_sin_darla_por_inexistente(self):
        r, _ = self.buscar('apt list --installed', 'zzz', snap=SNAPS, apt='vim/stable 9 amd64 [installed]')
        self.assertEqual(r['encontrado_en'], [])
        self.assertIn('AppImage', r['sin_rastro'])
        self.assertIn('otra parte del nombre', r['sin_rastro'])
        self.assertEqual(terminal_read.falta_tras(['apt list --installed'], r), [])

    def test_un_gestor_que_no_esta_instalado_no_es_una_busqueda_vacia(self):
        r, _ = self.buscar('apt list --installed', 'vlc', apt='vim/stable 9 amd64 [installed]', sin=('snap', 'flatpak'))
        self.assertEqual(r['tambien_mirado']['snap'], 'este equipo no tiene snap')
        self.assertEqual(r['tambien_mirado']['flatpak'], 'este equipo no tiene flatpak')

    def test_solo_un_lanzador_tambien_cuenta_como_encontrada(self):
        # Un AppImage integrado en el menú no está en ningún gestor.
        r, _ = self.buscar('apt list --installed', 'cursor', apt='vim/stable 9 amd64 [installed]',
                           lanzadores=['/home/u/.local/share/applications/cursor.desktop'])
        self.assertEqual(r['encontrado_en'], ['lanzadores'])
        self.assertNotIn('sin_rastro', r)

    def test_restos_de_configuracion_en_dpkg_no_son_una_aplicacion_instalada(self):
        r, _ = self.buscar('dpkg -l', 'gimp', dpkg='rc  gimp  3.0  amd64  editor\nii  vim  9  amd64  editor')
        self.assertEqual(r['encontrado_en'], [])
        self.assertIn('desinstalada', r['solo_restos'])
        self.assertEqual(r['lines'], 1)          # la línea rc se sigue enseñando tal cual

    def test_el_ruido_de_apt_no_se_cuenta_como_coincidencia(self):
        r, _ = self.buscar('snap list', 'list', snap=SNAPS, apt='vim/stable 9 amd64 [installed]')
        self.assertEqual(r['tambien_mirado']['apt'], 'sin coincidencias')

    def test_las_coincidencias_de_otro_gestor_se_acotan(self):
        r, _ = self.buscar('snap list', 'lib', snap=SNAPS,
                           apt='\n'.join('lib%d/stable 1 amd64 [installed]' % i for i in range(40)))
        self.assertEqual(len(r['tambien_mirado']['apt']), terminal_read.MAX_COINCIDENCIAS)

    def test_listado_sin_filter_no_encadena_y_dice_como_buscar(self):
        runner, vistas = equipo(snap=SNAPS)
        r = terminal_read.read('snap list', runner=runner)
        self.assertEqual(vistas, ['snap list'])
        self.assertIn('filter=', r['para_buscar'])
        self.assertNotIn('encontrado_en', r)
        self.assertEqual(terminal_read.falta_tras(['snap list'], r), ['apt', 'flatpak'])

    def test_lo_que_no_es_un_listado_de_instaladas_no_encadena(self):
        for orden in ('apt-cache search video', 'apt list', 'dpkg -s vim', 'snap info vlc', 'df -h',
                      'journalctl -u ssh -n 20'):
            vistas = []
            r = terminal_read.read(orden, filter='x', runner=lambda p: (vistas.append(p), (0, 'x'))[1])
            self.assertEqual(len(vistas), 1, orden)
            self.assertNotIn('encontrado_en', r, orden)
            self.assertNotIn('para_buscar', r, orden)

    def test_lanzadores_mira_nombres_de_archivo_y_nada_mas(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for nombre in ('ChatGPT.desktop', 'vim.desktop', 'chatgpt.txt'):
                open(os.path.join(tmp, nombre), 'w').close()
            self.assertEqual(terminal_read.lanzadores('chatgpt', (tmp, tmp + '/no-existe')),
                             [os.path.join(tmp, 'ChatGPT.desktop')])


class GrepComoFiltroTest(unittest.TestCase):
    """`orden | grep texto` se lee como filter; ninguna otra tubería pasa."""

    def test_se_traduce_y_se_dice(self):
        for orden in ('dpkg -l | grep gimp', 'dpkg -l|grep -i GIMP', "dpkg -l | grep 'gimp'", 'dpkg -l | grep "gimp" '):
            vistas = []
            r = terminal_read.read(orden, runner=lambda p: (vistas.append(p), (0, 'ii gimp 3\nii vim 9'))[1],
                                   escritorio=lambda t: [])
            self.assertEqual(vistas[0], ['dpkg', '-l'], orden)
            self.assertEqual(r['filter'].casefold(), 'gimp', orden)
            self.assertEqual(r['command'], 'dpkg -l', orden)
            self.assertIn('usa filter', r['nota'], orden)
            self.assertIn('apt', r['encontrado_en'], orden)

    def test_con_el_mismo_filter_repetido_tambien(self):
        r = terminal_read.read('snap list | grep vlc', filter='vlc', runner=lambda p: (0, 'vlc 3'), escritorio=lambda t: [])
        self.assertEqual((r['command'], r['filter']), ('snap list', 'vlc'))

    def test_lo_que_no_es_esa_forma_exacta_se_sigue_rechazando(self):
        for orden in ('dpkg -l | grep gimp | wc -l', 'dpkg -l | grep -v gimp', 'dpkg -l | grep -r x /etc',
                      'dpkg -l | grep gimp > /tmp/x', 'dpkg -l | grep $(rm x)', 'dpkg -l | grep gimp; rm x',
                      'dpkg -l | head', 'ls ; rm x | grep x', 'dpkg -l | grep gimp /etc/shadow',
                      'dpkg -l || apt list --installed', 'dpkg -l | grep `id`'):
            with self.assertRaisesRegex(ValueError, 'tuberías', msg=orden):
                terminal_read.read(orden, runner=lambda p: self.fail('no debía ejecutarse: ' + orden))

    def test_la_orden_que_queda_pasa_por_la_lista_de_siempre(self):
        for orden in ('rm -rf / | grep x', 'cat /etc/shadow | grep root', 'apt remove gimp | grep gimp'):
            with self.assertRaises(ValueError, msg=orden):
                terminal_read.read(orden, runner=lambda p: self.fail('no debía ejecutarse: ' + orden))

    def test_un_filter_distinto_del_grep_no_se_adivina(self):
        with self.assertRaisesRegex(ValueError, 'tuberías'):
            terminal_read.read('dpkg -l | grep gimp', filter='vim', runner=lambda p: self.fail('no'))


if __name__ == '__main__':
    unittest.main()
