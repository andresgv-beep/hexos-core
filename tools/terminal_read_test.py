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

    def test_orden_real_del_sistema(self):
        r = terminal_read.read('uname -r')
        self.assertEqual(r['exit_code'], 0)
        self.assertTrue(r['output'].strip())


if __name__ == '__main__':
    unittest.main()
