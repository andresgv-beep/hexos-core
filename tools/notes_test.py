"""Notas del núcleo: guardar, retocar sin destruir, y que lo guardado se relea."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import notes
from hexos.agent.work import WorkStore


class NotasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-notas-')
        self.addCleanup(self.tmp.cleanup)
        self.store = WorkStore(self.tmp.name)
        self.addCleanup(self.store.close)
        notes.initialize(self.store)

    def crear(self, title='Cambiar el cable de sda', body='El disco pierde el enlace.'):
        return notes.dispatch(self.store, 'note.save', dict(title=title, body=body), 'turno-1')

    def test_una_nota_nueva_nace_pendiente_y_se_relee(self):
        n = self.crear()
        self.assertTrue(n['created'])
        self.assertEqual(n['state'], 'pendiente')
        self.assertEqual(n['revision'], 1)
        # La prueba de que se guardó no es que no fallara: es haberlo releído.
        self.assertEqual(n['outcome'], 'hecho')
        self.assertIn('releído del almacén', n['checked'])

    def test_retocar_no_destruye_la_version_anterior(self):
        n = self.crear()
        notes.dispatch(self.store, 'note.save',
                       dict(id=n['id'], body='El disco pierde el enlace. Cable pedido.'), 'turno-2')
        cuerpos = [r['body'] for r in notes.history(self.store, n['id'])]
        self.assertEqual(cuerpos, ['El disco pierde el enlace.',
                                   'El disco pierde el enlace. Cable pedido.'])

    def test_retocar_solo_el_titulo_conserva_el_cuerpo(self):
        n = self.crear()
        r = notes.dispatch(self.store, 'note.save', dict(id=n['id'], title='Cable de sda'), 'turno-2')
        self.assertEqual(r['body'], 'El disco pierde el enlace.')
        self.assertEqual(r['revision'], 2)

    def test_editar_sobre_una_version_vieja_se_rechaza(self):
        n = self.crear()
        notes.dispatch(self.store, 'note.save', dict(id=n['id'], body='otra cosa'), 'turno-2')
        with self.assertRaises(ValueError) as e:
            notes.dispatch(self.store, 'note.save',
                           dict(id=n['id'], body='tercera', revision=n['revision']), 'turno-3')
        self.assertIn('cambió desde que la leíste', str(e.exception))

    def test_descartar_la_saca_de_la_lista_pero_no_borra_el_texto(self):
        n = self.crear()
        notes.dispatch(self.store, 'note.mark', dict(id=n['id'], state='descartada'), 'turno-2')
        self.assertEqual(notes.dispatch(self.store, 'note.list', {}, 't')['notes'], [])
        # Sigue ahí, y se puede pedir a propósito.
        pedidas = notes.dispatch(self.store, 'note.list', dict(state='descartada'), 't')['notes']
        self.assertEqual([x['id'] for x in pedidas], [n['id']])
        self.assertEqual(notes.get(self.store, n['id'])['body'], 'El disco pierde el enlace.')

    def test_anclar_a_favoritos_se_comprueba_releyendo(self):
        n = self.crear()
        r = notes.dispatch(self.store, 'note.mark', dict(id=n['id'], favorite=True), 'turno-2')
        self.assertTrue(r['favorite'])
        self.assertEqual(r['outcome'], 'hecho')
        anclada = notes.dispatch(self.store, 'note.list', dict(favorite=True), 't')['notes']
        self.assertEqual([x['id'] for x in anclada], [n['id']])

    def test_la_lista_recorta_el_cuerpo_y_lo_dice(self):
        self.crear(body='x' * 500)
        fila = notes.dispatch(self.store, 'note.list', {}, 't')['notes'][0]
        self.assertEqual(len(fila['body']), 300)
        self.assertTrue(fila['truncated'])

    def test_buscar_mira_titulo_cuerpo_y_etiquetas(self):
        self.crear()
        notes.dispatch(self.store, 'note.save',
                       dict(title='Comprar pan', body='del bueno', tags=['casa']), 't')
        for consulta, cuantas in (('sda', 1), ('casa', 1), ('disco', 1), ('zzz', 0)):
            with self.subTest(consulta):
                self.assertEqual(len(notes.dispatch(self.store, 'note.list',
                                                    dict(query=consulta), 't')['notes']), cuantas)

    def test_una_nota_nueva_sin_texto_no_se_crea(self):
        with self.assertRaises(ValueError):
            notes.dispatch(self.store, 'note.save', dict(title='sola'), 't')

    def test_estado_inventado_se_rechaza(self):
        n = self.crear()
        with self.assertRaises(ValueError) as e:
            notes.dispatch(self.store, 'note.mark', dict(id=n['id'], state='archivada'), 't')
        self.assertIn('pendiente', str(e.exception))

    def test_tocar_una_nota_que_no_existe_no_crea_una(self):
        with self.assertRaises(ValueError):
            notes.dispatch(self.store, 'note.save', dict(id='inventado', body='hola'), 't')
        self.assertEqual(notes.dispatch(self.store, 'note.list', {}, 't')['total'], 0)


class NucleoTest(unittest.TestCase):
    """El recuento del núcleo: uno solo, el mismo que responde y el que pinta."""

    def setUp(self):
        from hexos.agent import core, procedures, workflow
        self.core = core
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-nucleo-')
        self.addCleanup(self.tmp.cleanup)
        self.store = WorkStore(self.tmp.name)
        self.addCleanup(self.store.close)
        self.store.db.executescript(
            'CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, ts TEXT, content TEXT, sha256 TEXT);')
        notes.initialize(self.store)
        procedures.initialize(self.store)
        workflow.initialize(self.store)

    def test_cuenta_lo_que_hay_y_deja_fuera_lo_descartado(self):
        a = notes.dispatch(self.store, 'note.save', dict(title='una', body='x'), 't')
        notes.dispatch(self.store, 'note.save', dict(title='dos', body='y'), 't')
        notes.dispatch(self.store, 'note.mark', dict(id=a['id'], state='descartada'), 't')
        seccion = next(s for s in self.core.overview(self.store)['sections'] if s['key'] == 'notas')
        self.assertEqual((seccion['total'], seccion['pending']), (1, 1))

    def test_los_favoritos_salen_con_lo_justo_para_pintar_la_tira(self):
        n = notes.dispatch(self.store, 'note.save', dict(title='Cable de sda', body='x'), 't')
        notes.dispatch(self.store, 'note.mark', dict(id=n['id'], favorite=True), 't')
        r = self.core.overview(self.store)
        self.assertEqual(r['total_favorites'], 1)
        self.assertEqual(r['favorites'][0]['title'], 'Cable de sda')
        self.assertEqual(r['favorites'][0]['kind'], 'nota')

    def test_sin_perfil_dice_que_no_sabe_en_vez_de_contar_cero(self):
        perfil = next(s for s in self.core.overview(self.store)['sections'] if s['key'] == 'perfil')
        self.assertIsNone(perfil['total'])
        self.assertIn('no hay perfil', perfil['unknown'])

    def test_un_perfil_que_no_se_deja_leer_no_se_cuenta_como_vacio(self):
        class Roto:
            def keys(self): raise RuntimeError('hera no responde')
        perfil = next(s for s in self.core.overview(self.store, Roto())['sections'] if s['key'] == 'perfil')
        self.assertIsNone(perfil['total'])
        self.assertIn('hera no responde', perfil['unknown'])

    def test_los_hechos_ilegibles_se_declaran_aparte(self):
        class Parcial:
            unreadable = ['fila rota']
            def keys(self): return {'yo/nombre': 'Andrés'}
        perfil = next(s for s in self.core.overview(self.store, Parcial())['sections'] if s['key'] == 'perfil')
        self.assertEqual((perfil['total'], perfil['unreadable']), (1, 1))

    def test_no_promete_archivos_del_nas(self):
        r = self.core.overview(self.store)
        self.assertIn('No incluye archivos del NAS', r['note'])
        self.assertNotIn('fotos', [s['key'] for s in r['sections']])


class AfirmacionSinTrazaTest(unittest.TestCase):
    """Decir «lo he guardado» no guarda nada, y quien lee la respuesta no puede saberlo."""

    def cerrar(self, reply, trace):
        from hexos.agent.chat import Agent
        return Agent.closure(trace, reply)

    LECTURA = [dict(tool='nas.read', verification='no_requerida')]
    ESCRITURA = [dict(tool='note.save', verification='confirmada')]

    def test_canta_una_nota_que_no_guardó(self):
        cierre = self.cerrar('He recopilado el estado y la he guardado en una nota.', self.LECTURA)
        self.assertEqual(cierre['reason'], 'no_consta')
        self.assertIn('no se ejecutó ninguna operación de escritura', cierre['note'])
        # Y dice qué SÍ pasó, para que se vea de dónde sale la duda.
        self.assertIn('nas.read', cierre['note'])

    def test_si_de_verdad_escribió_no_se_le_reprocha(self):
        self.assertEqual(self.cerrar('He guardado la nota.', self.ESCRITURA)['reason'], 'comprobado')

    def test_una_escritura_distinta_tambien_sostiene_la_frase(self):
        # HexOS no juzga si la escritura era LA correcta: solo si hubo alguna.
        trace = [dict(tool='nas.container', verification='confirmada')]
        self.assertEqual(self.cerrar('He reiniciado el contenedor.', trace)['reason'], 'comprobado')

    def test_responder_sin_afirmar_nada_no_dispara_la_red(self):
        for texto in ('Aquí tienes el estado del NAS.',
                      'El disco sda pierde el enlace; conviene cambiar el cable.',
                      '¿Quieres que lo guarde en una nota?'):
            with self.subTest(texto):
                self.assertEqual(self.cerrar(texto, self.LECTURA)['reason'], 'comprobado')

    def test_un_turno_sin_herramientas_que_afirma_haber_guardado(self):
        cierre = self.cerrar('Listo, lo he apuntado.', [])
        self.assertEqual(cierre['reason'], 'no_consta')
        self.assertIn('no se ejecutó ninguna herramienta', cierre['note'])

    def test_la_frase_con_la_que_falló_de_verdad(self):
        # Salida real de Helios, 14/09/2026: respondió de memoria, sin ejecutar nada,
        # y dio por guardado lo que nunca guardó.
        cierre = self.cerrar('Ya te había preparado y guardado esa información. '
                             'Aquí tienes de nuevo el resumen completo.', [])
        self.assertEqual(cierre['reason'], 'no_consta')
        self.assertIn('compruébalo en el núcleo', cierre['note'])

    def test_lo_que_hizo_el_NAS_no_es_lo_que_hizo_helios(self):
        # Salida real, 14/09/2026: una revisión sin nada que guardar disparaba la red
        # por «el sistema ha registrado», que habla del NAS y no de Helios.
        for texto in ('El sistema ha registrado múltiples eventos de desconexión.',
                      'El kernel ha reiniciado el enlace varias veces.',
                      'DSM ha creado una instantánea automática.',
                      'He vuelto a revisar srv1 y sigue igual.',
                      # «registrar» lo hace también un NAS en su log: fuera de las
                      # formas impersonales, solo cuenta en primera persona.
                      'El evento quedó registrado en el kernel.'):
            with self.subTest(texto):
                self.assertEqual(self.cerrar(texto, self.LECTURA)['reason'], 'comprobado')

    def test_las_formas_reales_del_14_de_septiembre(self):
        # Turnos suyos con CERO herramientas y estas dos respuestas. Ninguna saltaba.
        for texto in ('He tomado nota de todo lo que hemos hablado, Andrés.',
                      'Ya he ajustado mi modo de conversación para ser más cercano.'):
            with self.subTest(texto):
                self.assertEqual(self.cerrar(texto, [])['reason'], 'no_consta')

    def test_negar_haberlo_guardado_no_es_afirmarlo(self):
        for texto in ('No he guardado nada todavía.', 'No he tomado nota de eso.'):
            with self.subTest(texto):
                self.assertEqual(self.cerrar(texto, self.LECTURA)['reason'], 'comprobado')

    def test_las_formas_con_las_que_este_modelo_canta_una_escritura(self):
        for texto in ('La he guardado en una nota.', 'He anotado el problema.',
                      'Te había preparado y guardado esa información.',
                      'Ya la había creado.', 'Hemos actualizado la nota.',
                      'He apuntado lo que me dices.', 'He creado la nota.',
                      'He reiniciado el contenedor.', 'Quedó guardada.'):
            with self.subTest(texto):
                self.assertEqual(self.cerrar(texto, self.LECTURA)['reason'], 'no_consta')


class PromesaIncumplidaTest(unittest.TestCase):
    """Anunciar el segundo paso y cerrar el turno deja a la persona esperando."""

    def mirar(self, reply, trace=None):
        from hexos.agent.chat import Agent
        return Agent.unfulfilled_promise(reply, trace if trace is not None else [dict(tool='nas.read')])

    def test_la_frase_real_con_la_que_dejó_a_medias(self):
        # Turno del 15/09/2026: una lectura, y esto. No volvió.
        self.assertTrue(self.mirar('Ya tengo el diagnóstico de servidorsrv1. Ahora voy a revisar '
                                   'el estado de sus contenedores.\n\nDame un momento, Andrés.'))

    def test_las_formas_de_prometer_una_acción(self):
        for texto in ('Voy a consultar el NAS.', 'Paso a revisar los contenedores.',
                      'Ahora mismo compruebo el disco.', 'Procedo a reiniciar el contenedor.',
                      'Enseguida te digo.'):
            with self.subTest(texto):
                self.assertTrue(self.mirar(texto), texto)

    def test_preguntar_no_es_prometer(self):
        for texto in ('¿Quieres que revise los contenedores?',
                      '¿Voy a revisar el NAS o prefieres esperar?'):
            with self.subTest(texto):
                self.assertIsNone(self.mirar(texto))

    def test_un_verbo_sin_herramienta_detrás_no_cuenta(self):
        for texto in ('Voy a explicarte lo que pasa.', 'Vamos a necesitar la contraseña.',
                      'Voy a ser más breve a partir de ahora.'):
            with self.subTest(texto):
                self.assertIsNone(self.mirar(texto))

    def test_una_promesa_vieja_en_medio_de_una_respuesta_larga_no_cuenta(self):
        # Solo la cola: si prometió y DESPUÉS hizo y contó, el turno está bien.
        largo = 'Voy a revisar el NAS. ' + 'Encontré tres contenedores parados y los detallo. ' * 8
        self.assertIsNone(self.mirar(largo))

    def test_sin_margen_de_herramientas_no_hay_turno_que_devolver(self):
        self.assertIsNone(self.mirar('Ahora voy a revisar los contenedores.',
                                     [dict(tool='nas.read')] * 6))


class AnuncioSinLlamadaTest(unittest.TestCase):
    """Dijo que abría la nota y no la abrió: la pantalla no cambió."""

    def mirar(self, reply, trace=None):
        from hexos.agent.chat import Agent
        return Agent.announced_without_call(reply, trace or [])

    def test_sus_cuatro_frases_reales(self):
        # Turnos del 15/09/2026, todos con CERO herramientas en la traza.
        for texto, esperada in (
                ('Te voy a abrir la nota "Actualización de Estado de srv1".', 'note.show'),
                ('Te muestro la nota "Problema de disco Synology".', 'note.show'),
                ('Te la enseño ahora mismo.', 'note.show'),
                ('He cerrado la nota.', 'note.hide')):
            with self.subTest(texto):
                resultado = self.mirar(texto)
                self.assertIsNotNone(resultado, texto)
                self.assertEqual(resultado[1], esperada)

    def test_si_la_llamó_no_se_le_reprocha(self):
        self.assertIsNone(self.mirar('Te muestro la nota.', [dict(tool='note.show')]))

    def test_pedir_permiso_no_es_anunciar(self):
        for texto in ('¿Te la abro?', '¿Quieres que te muestre la nota?'):
            with self.subTest(texto):
                self.assertIsNone(self.mirar(texto))

    def test_una_llamada_fallida_no_cuenta_como_hecha(self):
        self.assertIsNotNone(self.mirar('Te muestro la nota.',
                                        [dict(tool='note.show', failed=True)]))

    def test_exige_LA_herramienta_anunciada_no_una_cualquiera(self):
        # Guardar una nota no cumple «te la abro».
        self.assertEqual(self.mirar('Te la abro.', [dict(tool='note.save')])[1], 'note.show')


class NotaSenaladaTest(unittest.TestCase):
    """«Ábrela» señala a algo que está en la traza; traducirlo no es elegir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-senala-')
        self.addCleanup(self.tmp.cleanup)
        from hexos.agent.chat import Agent
        self.agent = Agent(self.tmp.name, None)

    def con_traza(self, pasos, texto):
        import json as _json
        with self.agent.store() as s:
            s.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', ('previo','t','user','x','x'))
            for paso in pasos:
                s.db.execute('INSERT INTO tool_events(turn_id,ts,body) VALUES (?,?,?)',
                             ('previo', 't', _json.dumps(paso)))
            s.db.commit()
            return self.agent.pointed_note(s, texto, 'ahora')

    LISTA = dict(tool='note.list', result=dict(notes=[
        dict(id='aaa', title='Actualización de srv1'),
        dict(id='bbb', title='Informe completo'),
        dict(id='ccc', title='Problema de disco Synology')]))

    def test_la_3_es_la_tercera_que_vio(self):
        self.assertEqual(self.con_traza([self.LISTA], 'mustrame la 3')['id'], 'ccc')

    def test_abrela_señala_a_la_que_se_acaba_de_abrir(self):
        pasos = [dict(tool='note.show', result=dict(id='bbb', title='Informe completo'))]
        self.assertEqual(self.con_traza(pasos, 'abrela')['id'], 'bbb')

    def test_con_varias_listadas_y_sin_ordinal_no_se_elige_ninguna(self):
        # Señalar «esa» sobre una lista de tres no señala a ninguna: se pregunta.
        self.assertIsNone(self.con_traza([self.LISTA], 'abre esa nota'))

    def test_un_ordinal_fuera_de_la_lista_no_inventa(self):
        self.assertIsNone(self.con_traza([self.LISTA], 'mustrame la 9'))

    def test_sin_pronombre_no_se_toca_nada(self):
        self.assertIsNone(self.con_traza([self.LISTA], 'muestrame la nota del disco'))

    def test_sin_traza_previa_no_hay_a_qué_señalar(self):
        self.assertIsNone(self.con_traza([], 'abrela'))


if __name__ == '__main__':
    unittest.main()
