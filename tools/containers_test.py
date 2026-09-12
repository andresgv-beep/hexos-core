import unittest

from hexos.agent.nas_session import command, container_rows, present_result

BANNER = ('** WARNING: connection is not using a post-quantum key exchange algorithm.\r\n'
          '** This session may be vulnerable to "store now, decrypt later" attacks.\r\n'
          "helios@192.168.1.243's  \r\n"
          'Could not chdir to home directory /var/services/homes/helios: No such file or directory\r\n')
CLOSE = 'Connection to 192.168.1.243 closed.\r\n'


def action_output(name, state, status):
    return BANNER + name + '\r\n__HEXOS_STATE__\r\n' + name + '\t' + state + '\t' + status + '\r\n' + CLOSE


def acted(name, action, state, status, exit_code=0):
    return present_result(dict(section='container', container=name, action=action, exit_code=exit_code,
                               output=action_output(name, state, status)), 'container')


class ContainersTest(unittest.TestCase):
    def test_ssh_banner_is_not_confused_with_container_rows(self):
        rows, _ = container_rows(BANNER + 'plex\trunning\tUp 2 days\r\n' + CLOSE)
        self.assertEqual(rows, [dict(name='plex', state='running', status='Up 2 days')])

    def test_a_start_that_holds_is_reported_as_done(self):
        result = acted('plex', 'start', 'running', 'Up 1 second')
        self.assertEqual(result['outcome'], 'hecho')
        self.assertIsNone(result['warning'])
        self.assertEqual(result['container_state']['state'], 'running')
        # El ruido de la sesión SSH no llega al modelo.
        self.assertNotIn('output', result)

    def test_a_start_that_falls_back_is_not_reported_as_success(self):
        # docker devuelve 0 y escribe el nombre aunque el contenedor salga acto seguido.
        result = acted('HandBrake', 'start', 'exited', 'Exited (0) 1 second ago')
        self.assertEqual(result['outcome'], 'no_se_sostuvo')
        self.assertIn('volvió a salir', result['warning'])

    def test_stopping_expects_the_opposite_state(self):
        result = acted('plex', 'stop', 'exited', 'Exited (0) 1 second ago')
        self.assertEqual(result['outcome'], 'hecho')
        self.assertIsNone(result['warning'])

    def test_unknown_container_is_not_confirmed(self):
        result = present_result(dict(section='container', container='x', action='start', exit_code=1,
                                     output=BANNER + 'Error: No such container: x\r\n__HEXOS_STATE__\r\n'), 'container')
        self.assertEqual(result['outcome'], 'sin_confirmar')
        self.assertIsNone(result['container_state'])

    def test_listing_returns_rows_instead_of_raw_terminal_output(self):
        result = present_result(dict(section='containers', exit_code=0, output=BANNER +
                                     'minecraft-java\trunning\tUp 2 days (healthy)\r\n'
                                     'portainer\tcreated\tCreated\r\n' + CLOSE), 'containers')
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['containers'][1], dict(name='portainer', state='created', status='Created'))
        self.assertNotIn('output', result)

    def test_one_container_can_be_checked_without_touching_it(self):
        # Comprobar no debe exigir una acción: era lo que empujaba a reiniciar al verificar.
        remote = command('containers', container='HandBrake')
        self.assertIn('ps -a --filter name=HandBrake', remote)
        for forbidden in ('start', 'stop', 'restart'):
            self.assertNotIn('$D ' + forbidden, remote)

    def test_checking_rejects_a_name_that_could_reach_the_shell(self):
        for bad in ('HandBrake; rm -rf /', '-v/:/host', '$(id)'):
            with self.assertRaises(ValueError):
                command('containers', container=bad)

    def test_the_write_tool_says_it_is_not_for_checking(self):
        from hexos.agent import catalog
        write = catalog.TOOLS['nas.container']['description']
        self.assertIn('NO sirve para comprobar', write)
        self.assertIn('nas.read', write)
        self.assertIn('container', catalog.TOOLS['nas.read']['optional'])

    def test_the_action_also_reads_the_resulting_state(self):
        remote = command('container', container='plex', action='restart')
        self.assertIn('$D restart -- plex', remote)
        self.assertIn('__HEXOS_STATE__', remote)
        self.assertIn('ps -a --filter name=plex', remote)


if __name__ == '__main__':
    unittest.main()
