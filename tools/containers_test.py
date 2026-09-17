import unittest

import tempfile
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


class EfectoDesconocidoTest(unittest.TestCase):
    """Un timeout en una escritura no es fallo ni éxito: es no saber."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-efecto-')
        class Runtime:
            def call(self, request): pass
            def generate(self, messages): return {'reply': '', 'work': None}
        from hexos.agent.chat import Agent
        self.agent = Agent(self.tmp.name, Runtime())

    def tearDown(self):
        self.tmp.cleanup()

    def actuar(self, salida, **extra):
        from unittest.mock import patch
        with self.agent.store() as store:
            with patch('hexos.agent.chat.nas_read', return_value=salida):
                return self.agent.tool(store, 'nas.container',
                                       dict(device='synology', container='handbrake',
                                            action='restart', **extra),
                                       turn_id='u1')

    def test_el_timeout_queda_anotado_mas_alla_del_turno(self):
        self.actuar(dict(outcome='desconocido', container='handbrake', action='restart'))
        with self.agent.store() as store:
            fila = self.agent.pending_effect(store, 'synology', 'handbrake')
        self.assertIsNotNone(fila, 'el riesgo no caduca al responder')
        self.assertEqual(fila['action'], 'restart')

    def test_no_se_repite_a_ciegas_y_dice_qué_lectura_lo_aclara(self):
        self.actuar(dict(outcome='desconocido', container='handbrake', action='restart'))
        with self.assertRaises(ValueError) as caught:
            self.actuar(dict(outcome='hecho', container='handbrake', action='restart'))
        mensaje = str(caught.exception)
        self.assertIn('no consta si llegó a ejecutarse', mensaje)
        self.assertIn('section=containers', mensaje)

    def test_una_lectura_posterior_lo_cierra(self):
        from unittest.mock import patch
        self.actuar(dict(outcome='desconocido', container='handbrake', action='restart'))
        with self.agent.store() as store:
            with patch('hexos.agent.chat.nas_read', return_value=dict(
                    container='handbrake',
                    container_state=dict(name='handbrake', state='running', status='Up 2 seconds'))):
                self.agent.tool(store, 'nas.read',
                                dict(device='synology', section='containers',
                                     container='handbrake'), turn_id='u2')
            self.assertIsNone(self.agent.pending_effect(store, 'synology', 'handbrake'))
        # Y una vez aclarado, la escritura vuelve a estar permitida.
        self.actuar(dict(outcome='hecho', container='handbrake', action='restart'))

    def test_un_resultado_normal_no_deja_nada_colgando(self):
        self.actuar(dict(outcome='hecho', container='handbrake', action='restart',
                         container_state=dict(name='handbrake', state='running', status='Up 2 seconds')))
        with self.agent.store() as store:
            self.assertIsNone(self.agent.pending_effect(store, 'synology', 'handbrake'))


class ReinicioComprobadoTest(unittest.TestCase):
    """Ver «running» no demuestra un reinicio; el tiempo de vida sí."""

    def resultado(self, status, action='restart', exit_code=0):
        from hexos.agent.nas_session import present_result
        # `docker restart` solo imprime el nombre; la tabla viene tras el marcador.
        salida = 'handbrake\n__HEXOS_STATE__\nhandbrake\trunning\t' + status + '\n'
        return present_result(dict(output=salida, container='handbrake', action=action,
                                   exit_code=exit_code, timed_out=False), 'container')

    def test_un_reinicio_de_verdad_se_confirma(self):
        self.assertEqual(self.resultado('Up 2 seconds')['outcome'], 'hecho')

    def test_uno_que_ya_llevaba_semanas_arriba_no_cuenta_como_reiniciado(self):
        # El caso que se colaba: seguía running, así que se daba por hecho.
        self.assertEqual(self.resultado('Up 2 weeks')['outcome'], 'sin_confirmar')

    def test_parar_no_exige_tiempo_de_vida_nuevo(self):
        from hexos.agent.nas_session import present_result
        salida = 'handbrake\n__HEXOS_STATE__\nhandbrake\texited\tExited (0) 1 second ago\n'
        r = present_result(dict(output=salida, container='handbrake', action='stop',
                                exit_code=0, timed_out=False), 'container')
        self.assertEqual(r['outcome'], 'hecho')

    def test_un_timeout_no_se_lee_como_exito_ni_como_fallo(self):
        from hexos.agent.nas_session import present_result
        r = present_result(dict(output='', container='handbrake', action='restart',
                                exit_code=None, timed_out=True), 'container')
        self.assertEqual(r['outcome'], 'desconocido')


class PreguntasAbiertasTest(unittest.TestCase):
    """Un listado debe decir lo que NO responde, o no hay por dónde investigar."""

    def listar(self, filas):
        from hexos.agent.nas_session import present_result
        salida = '\n'.join('\t'.join(f) for f in filas) + '\n'
        return present_result(dict(output=salida, exit_code=0, timed_out=False), 'containers')

    def test_un_parado_abre_una_pregunta_y_dice_con_qué_seguir(self):
        r = self.listar([('HandBrake', 'exited', 'Exited (0) 40 hours ago', 'img'),
                         ('n8n', 'running', 'Up 2 weeks', 'img')])
        preguntas = {q['about']: q for q in r['open_questions']}
        self.assertEqual(list(preguntas), ['HandBrake'], 'lo que corre no abre preguntas')
        self.assertIn('no dice si fue a propósito', preguntas['HandBrake']['unknown'])
        self.assertIn('container=HandBrake', preguntas['HandBrake']['ask'])
        # Y se dice lo que NO se puede leer, en vez de dejarlo suponer.
        self.assertIn('registros del contenedor no se pueden leer', preguntas['HandBrake']['ask'])

    def test_el_codigo_de_salida_distingue_una_parada_limpia_de_una_muerte(self):
        r = self.listar([('a', 'exited', 'Exited (0) 1 hour ago', 'img'),
                         ('b', 'exited', 'Exited (137) 1 hour ago', 'img')])
        porNombre = {c['name']: c.get('ended') for c in r['containers']}
        self.assertEqual(porNombre['a']['exit_code'], 0)
        self.assertIn('sin error', porNombre['a']['reading'])
        self.assertEqual(porNombre['b']['exit_code'], 137)
        self.assertIn('mataron', porNombre['b']['reading'])

    def test_un_codigo_que_no_conozco_no_se_interpreta(self):
        r = self.listar([('a', 'exited', 'Exited (99) 1 hour ago', 'img')])
        ended = r['containers'][0]['ended']
        self.assertNotIn('ended', self.listar([('n8n','running','Up 2 weeks','img')])['containers'][0])
        self.assertEqual(ended['exit_code'], 99)
        self.assertFalse(ended['known'])
        self.assertIsNone(ended['reading'], 'inventar una causa sería peor que callar')
        self.assertIn('no interpreto', r['open_questions'][0]['unknown'])

    def test_uno_que_nunca_arrancó_no_promete_una_lectura_que_no_existe(self):
        r = self.listar([('portainer', 'created', 'Created', 'img')])
        pregunta = r['open_questions'][0]
        self.assertIn('Nunca llegó a arrancar', pregunta['unknown'])
        self.assertIsNone(pregunta['ask'])

    def test_uno_en_bucle_se_señala_sin_afirmar_que_el_bucle_siga(self):
        # «fallo repetido» de la lista de aceptación: se veía `restarting` y pasaba
        # por el listado como un estado más.
        r = self.listar([('d', 'restarting', 'Restarting (1) 5 seconds ago', 'img')])
        fila = r['containers'][0]
        self.assertEqual(fila['restarting']['exit_code'], 1)
        pregunta = r['open_questions'][0]
        self.assertIn('levantando otra vez', pregunta['unknown'])
        # Un estado puntual no demuestra un bucle: puede ser el primer reintento.
        self.assertIn('puede ser el primer reintento', pregunta['unknown'])
        self.assertIn('no se pueden leer', pregunta['ask'])

    def test_un_codigo_de_caida_que_no_conozco_no_se_interpreta(self):
        r = self.listar([('f', 'restarting', 'Restarting (99) 2 seconds ago', 'img')])
        self.assertFalse(r['containers'][0]['restarting']['known'])
        self.assertIn('no interpreto', r['open_questions'][0]['unknown'])

    def test_el_healthy_se_marca_como_chequeo_de_docker(self):
        # Leerlo como garantía de que el servicio sirve es fácil, y es falso.
        r = self.listar([('e', 'running', 'Up 2 weeks (healthy)', 'img'),
                         ('n8n', 'running', 'Up 2 weeks', 'img')])
        porNombre = {c['name']: c for c in r['containers']}
        self.assertTrue(porNombre['e']['health_is_dockers'])
        self.assertNotIn('health_is_dockers', porNombre['n8n'])
        self.assertIn('no prueba de que el servicio funcione', r['note_state'])
        # Y estar sano según docker no abre preguntas: no es un problema.
        self.assertEqual(r['open_questions'], [])

    def test_sin_nada_parado_no_hay_preguntas_que_perseguir(self):
        r = self.listar([('n8n', 'running', 'Up 2 weeks', 'img')])
        self.assertEqual(r['open_questions'], [])


class EspacioTest(unittest.TestCase):
    """Uso por volumen: el porcentaje de cada uno, y lo que un porcentaje no dice."""

    SALIDA = ('Filesystem         1024-blocks      Used Available Capacity Mounted on\n'
              '/dev/md0               2385528   1109692   1157044      49% /\n'
              'devtmpfs               1928316         0   1928316       0% /dev\n'
              'tmpfs                  1938460         4   1938456       1% /dev/shm\n'
              '/dev/mapper/cachedev_0 3844673148 3500128220 344544928  92% /volume1\n'
              '/dev/mapper/cachedev_1 1922336574  230680388 1691656186  13% /volume2\n')

    def leer(self, salida=None):
        from hexos.agent.nas_session import present_result
        return present_result(dict(output=salida if salida is not None else self.SALIDA,
                                   exit_code=0, timed_out=False), 'space')

    def test_da_el_porcentaje_de_cada_volumen_y_los_ordena(self):
        r = self.leer()
        self.assertEqual([(v['mount'], v['percent']) for v in r['volumes']],
                         [('/volume1', 92), ('/', 49), ('/volume2', 13)])
        self.assertIn('/volume1 al 92%', r['headline'])

    def test_deja_fuera_el_ruido_del_sistema(self):
        # Un NAS monta decenas de tmpfs; meterlos convierte la respuesta en volcado.
        puntos = [v['mount'] for v in self.leer()['volumes']]
        self.assertNotIn('/dev', puntos)
        self.assertNotIn('/dev/shm', puntos)

    def test_los_tamaños_se_dan_legibles_sin_perder_el_número(self):
        v = next(v for v in self.leer()['volumes'] if v['mount'] == '/volume2')
        self.assertEqual(v['total_kib'], 1922336574)
        self.assertTrue(v['total'].endswith('TiB'))

    def test_solo_abre_pregunta_el_que_va_justo(self):
        r = self.leer()
        self.assertEqual([q['about'] for q in r['open_questions']], ['/volume1'])
        pregunta = r['open_questions'][0]
        # Una lectura no distingue «lleva años así» de «se llena esta semana».
        self.assertIn('ni si está creciendo', pregunta['unknown'])
        self.assertIn('no hay lectura de árbol de archivos', pregunta['ask'])

    def test_el_umbral_se_declara_como_convención(self):
        r = self.leer()
        self.assertEqual(r['threshold_pct'], 85)
        self.assertIn('convención elegida aquí, no una medida', r['note_space'])
        # Y btrfs puede informar de menos espacio del que parece.
        self.assertIn('instantáneas y los metadatos', r['note_space'])

    def test_una_salida_que_no_se_reconoce_no_se_inventa(self):
        r = self.leer('df: command not found\n')
        self.assertEqual(r['volumes'], [])
        self.assertIn('No se reconoció ningún volumen', r['headline'])
        # Y la salida cruda sobrevive: es la única pista de por qué no se reconoció.
        self.assertIn('command not found', r['output'])

    def test_cuando_se_entiende_la_salida_no_se_arrastra_el_volcado(self):
        self.assertNotIn('output', self.leer())


if __name__ == '__main__':
    unittest.main()
