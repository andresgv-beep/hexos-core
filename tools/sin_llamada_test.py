"""Ventana Agente: si el selector pidió herramientas y el turno acaba sin llamar, se devuelve."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.state import TurnState
from hexos.agent import native


class Runtime:
    def __init__(self, acepta=True): self.checks, self.acepta = 0, acepta
    def call(self, request): pass
    def require_check(self): self.checks += 1; return self.acepta


class SinLlamadaTest(unittest.TestCase):
    def cierre(self, *, ventana='agente', pedidos=('sistema',), traza=(), runtime=None,
               respuesta='Para revisar el registro usaré journalctl.'):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-llamada-')
        self.addCleanup(tmp.cleanup)
        runtime = runtime or Runtime()
        agent = Agent(tmp.name, runtime)
        agent.ventana = ventana
        turn = TurnState(text='mira el registro', image=None, model_request='mira el registro', transcript=None)
        turn.grupos_pedidos, turn.trace = list(pedidos), list(traza)
        salida = dict(reply=respuesta, work=None)
        primera = agent.runner.recovery.before_completion(None, turn, salida)
        return runtime, turn, primera, lambda: agent.runner.recovery.before_completion(None, turn, salida)

    def test_se_devuelve_una_vez_y_sin_forzar_una_lectura(self):
        # Con el historial real delante: «usaré journalctl. Voy a buscar…» y fin del turno.
        runtime, turn, devuelto, otra = self.cierre()
        self.assertTrue(devuelto)
        self.assertEqual(runtime.checks, 0)           # forzado, una charla llamaba a task_current
        self.assertIn('AVISO DE HEXOS', turn.messages[0]['content'])
        turn.trace.append(dict(tool='terminal.read', arguments={}, result={}, failed=False))
        turn.messages = []
        self.assertFalse(otra())                      # consultó: vale lo que diga ahora
        self.assertIsNotNone(turn.retries.respuesta_devuelta)

    def test_una_charla_en_el_agente_conserva_su_respuesta(self):
        # «¿y qué echas en falta?» -> «¿por ejemplo?»: la respuesta buena se cambió por
        # «No tengo un encargo activo en este momento».
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-llamada-'); self.addCleanup(tmp.cleanup)
        runtime = Runtime(); llamadas = []; runtime.call = llamadas.append
        agent = Agent(tmp.name, runtime); agent.ventana = 'agente'
        turn = TurnState(text='por ejemplo?', image=None, model_request='por ejemplo?', transcript=None)
        turn.grupos_pedidos = ['sistema']
        salida = dict(reply='Por ejemplo, una herramienta para cambiar un servicio.', work=None)
        self.assertTrue(agent.runner.recovery.before_completion(None, turn, salida))
        salida['reply'] = 'Entendido.'
        self.assertFalse(agent.runner.recovery.before_completion(None, turn, salida))
        self.assertEqual(salida['reply'], 'Por ejemplo, una herramienta para cambiar un servicio.')
        self.assertIn({'type': 'reset'}, llamadas)

    def test_busqueda_web_del_chat_se_devuelve_una_vez_incluso_con_recuerdo_automatico(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime()
            runtime.require_read = Mock(return_value=True)
            agent = Agent(tmp, runtime)
            agent.ventana = 'chat'
            turn = TurnState(text='Busca', busqueda_web_pedida=True)
            turn.trace = [dict(tool='history.recall', result={'matches': []})]
            recovery = agent.runner.recovery
            salida = dict(reply='Dame un segundo.', work=None)
            self.assertTrue(recovery.before_completion(None, turn, salida))
            self.assertIn('web_search', turn.messages[0]['content'])
            self.assertFalse(recovery.before_completion(None, turn, salida))
            runtime.require_read.assert_called_once_with('web.search')

            # Una búsqueda automática ya ejecutada sigue la ruta habitual de lectura de fuentes.
            turn = TurnState(text='Busca', busqueda_web_pedida=True)
            turn.trace = [dict(tool='web.search', arguments={}, result={'items': []}, failed=False)]
            self.assertTrue(recovery.before_completion(None, turn, salida))
            self.assertFalse(turn.retries.busqueda_web_devuelta)
            runtime.require_read.assert_called_once()

    def test_no_depende_de_lo_que_diga_la_respuesta(self):
        # Las frases no cuentan, ni para bien ni para mal: es una señal de estructura.
        for respuesta in ('Claro.', '¿De qué equipo hablas?', 'Voy a mirarlo ahora mismo.'):
            self.assertTrue(self.cierre(respuesta=respuesta)[2], respuesta)

    def test_una_respuesta_que_entrega_codigo_no_se_devuelve(self):
        # Visto con el 26B: cada página se generaba dos veces porque no había «consultado nada».
        pagina = 'Aquí tienes:\n\n```html\n<!DOCTYPE html>\n<html>\n<body>\n<canvas></canvas>\n<script>\n</script>\n</body>\n</html>\n```\n'
        runtime, turn, devuelto, _ = self.cierre(pedidos=('proyecto',), respuesta=pagina)
        self.assertFalse(devuelto)
        self.assertFalse(turn.messages)
        # Una orden suelta entre cercas sigue siendo «usaré journalctl»: no es una entrega.
        self.assertTrue(self.cierre(respuesta='Usaré esto:\n```\njournalctl -p err\n```\n')[2])

    def test_si_el_selector_no_pidio_nada_es_una_charla(self):
        runtime, _, devuelto, _ = self.cierre(pedidos=(), respuesta='Voy a revisar el NAS.')
        self.assertFalse(devuelto)
        self.assertEqual(runtime.checks, 0)

    def chat(self, respuesta, traza=()):
        runtime = Runtime(); runtime.native = True
        return self.cierre(ventana='chat', pedidos=('notas',), runtime=runtime,
                           respuesta=respuesta, traza=traza)

    def test_en_el_chat_se_devuelve_lo_que_dice_haber_guardado_sin_guardar(self):
        # Apuntar es escribir, y el arranque forzado solo deja leer: se avisa y elige.
        runtime, turn, devuelto, otra = self.chat('He apuntado que tienes dentista el viernes.')
        self.assertTrue(devuelto)
        self.assertEqual(runtime.checks, 0)
        self.assertIn('no se ha guardado nada', turn.messages[0]['content'])
        turn.messages = []
        self.assertFalse(otra())

    def test_si_repetir_no_hace_nada_se_entrega_la_primera_respuesta(self):
        # «Mil disculpas, lo he anotado mal: tú eres mi creador» se devolvió, y lo que
        # salió fue «Entendido. No he guardado nada en este turno».
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-llamada-'); self.addCleanup(tmp.cleanup)
        runtime = Runtime(); runtime.native = True
        llamadas = []
        runtime.call = llamadas.append
        agent = Agent(tmp.name, runtime); agent.ventana = 'chat'
        turn = TurnState(text='soy tu creador', image=None, model_request='soy tu creador', transcript=None)
        salida = dict(reply='Tienes razón, lo he anotado mal: tú eres mi creador.', work=None)
        self.assertTrue(agent.runner.recovery.before_completion(None, turn, salida))
        salida['reply'] = 'Entendido. No he guardado nada en este turno.'
        self.assertFalse(agent.runner.recovery.before_completion(None, turn, salida))
        self.assertEqual(salida['reply'], 'Tienes razón, lo he anotado mal: tú eres mi creador.')
        self.assertIn({'type': 'reset'}, llamadas)      # el aviso no se queda en la conversación

    def test_si_al_repetir_guarda_la_nota_vale_la_segunda(self):
        runtime, turn, devuelto, otra = self.chat('He apuntado que tienes dentista el viernes.')
        self.assertTrue(devuelto)
        turn.trace.append(dict(tool='note.save', arguments={}, result={'id': 'n1'}, failed=False))
        self.assertFalse(otra())
        self.assertIsNotNone(turn.retries.respuesta_devuelta)   # no se restauró la primera

    def orden(self, texto, respuesta='De acuerdo, lo anoto.', pedidos=('notas',), traza=()):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-llamada-'); self.addCleanup(tmp.cleanup)
        runtime = Runtime(); runtime.native = True; runtime.notas = 0
        def require_note(name='note.save'): runtime.notas += 1; runtime.pedida = name; return True
        runtime.require_note = require_note
        runtime.lecturas = []
        runtime.require_read = lambda name: runtime.lecturas.append(name) or True
        agent = Agent(tmp.name, runtime); agent.ventana = 'chat'
        turn = TurnState(text=texto, image=None, model_request=texto, transcript=None)
        turn.grupos_pedidos, turn.trace = list(pedidos), list(traza)
        self._recovery = agent.runner.recovery
        devuelto = agent.runner.recovery.before_completion(None, turn, dict(reply=respuesta, work=None))
        return runtime, turn, devuelto

    def agente_de(self, turn):
        return self._recovery

    def test_lectura_y_nota_solo_se_reintenta_el_paso_pendiente(self):
        texto = 'Busca la edición del manual y guarda su código en una nota.'
        fuente = dict(tool='web.read', result={'text': 'SC-8174'}, failed=False)
        runtime, turn, devuelto = self.orden(texto, traza=[fuente])
        self.assertTrue(devuelto)
        self.assertTrue(turn.retries.nota_tras_lectura)
        self.assertIn('note_save', turn.messages[0]['content'])
        self.assertEqual(runtime.notas, 0)  # no fuerza una escritura incondicional
        for pasos in ([dict(fuente, failed=True)], [fuente, dict(tool='note.save', failed=False, result={'id': 'n1'})]):
            self.assertFalse(self.orden(texto, traza=pasos)[1].retries.nota_tras_lectura)
        for msg in ('Lee el manual sin guardar una nota', texto + ' Solo si la edición está agotada.'):
            self.assertFalse(self.orden(msg, traza=[fuente])[1].retries.nota_tras_lectura)

    def test_cierre_parcial_si_lee_la_fuente_y_no_consigue_guardarla(self):
        from hexos.agent.chat_backend.state import AgentDependencies

        class Motor:
            def __init__(self):
                self.pasos = iter([
                    dict(tool='web.read', arguments=dict(url='https://example.org/manual')),
                    dict(reply='El código es SC-8174.', work=None),
                    dict(reply='El código es SC-8174.', work=None)])

            def call(self, request): pass
            def generate(self, messages): return next(self.pasos)

        with tempfile.TemporaryDirectory() as tmp:
            deps = AgentDependencies(web_read=lambda url: dict(url=url, text='SC-8174'))
            agente = Agent(tmp, Motor(), dependencies=deps)
            agente.set_window('agente')
            res = agente.chat('Lee el manual y guarda su código en una nota.')
            with agente.store() as store:
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM notes').fetchone()[0], 0)
        self.assertEqual(res['closure']['reason'], 'parcial')
        self.assertIn('SC-8174', res['reply'])
        self.assertIn('nota ha quedado pendiente', res['reply'])

    def test_si_ordeno_apuntar_y_no_se_guardo_se_arranca_en_la_nota(self):
        # «apúntame que mañana llamo a mamá» -> «De acuerdo, lo anoto.» y ninguna llamada.
        for texto in ('apunta que el viernes tengo dentista', 'anota: comprar pan',
                      'oye helios, apúntame que mañana llamo a mamá'):
            runtime, turn, devuelto = self.orden(texto)
            self.assertTrue(devuelto, texto)
            self.assertEqual(runtime.notas, 1)
            self.assertIn('todavía no se ha guardado nada', turn.messages[0]['content'])

    def test_si_la_nota_ya_esta_guardada_no_se_repite(self):
        traza = [dict(tool='note.save', arguments={}, result={'id': 'n1'}, failed=False)]
        runtime, _, devuelto = self.orden('apunta que tengo dentista', 'Anotado.', traza=traza)
        self.assertFalse(devuelto)
        self.assertEqual(runtime.notas, 0)

    LISTA = dict(tool='note.list', arguments={'query': 'cena'}, failed=False,
                 result={'notes': [{'n': 1, 'title': 'Cena con Marta', 'state': 'pendiente'}], 'total': 1})

    def test_si_ordeno_borrar_y_solo_la_busco_se_arranca_en_descartarla(self):
        # «borra la nota de la cena» -> note.list y «Voy a descartar la nota de la cena».
        for texto in ('borra la nota de la cena', 'elimina la de las plantas', 'helios, bórrame esa nota'):
            runtime, turn, devuelto = self.orden(texto, 'Voy a descartar la nota.', traza=[self.LISTA])
            self.assertTrue(devuelto, texto)
            self.assertEqual((runtime.notas, runtime.pedida), (1, 'note.mark'))
            self.assertIn('todavía no se ha descartado', turn.messages[0]['content'])

    def test_si_ya_la_descarto_no_se_repite(self):
        traza = [self.LISTA, dict(tool='note.mark', arguments={'n': 1, 'state': 'descartada'},
                                  result={'state': 'descartada'}, failed=False)]
        runtime, _, devuelto = self.orden('borra la nota de la cena', 'Descartada.', traza=traza)
        self.assertFalse(devuelto)
        self.assertEqual(runtime.notas, 0)

    def test_sin_una_nota_a_la_vista_no_se_arranca_un_borrado(self):
        vacia = dict(tool='note.list', arguments={'query': 'boda'}, failed=False, result={'notes': [], 'total': 0})
        runtime, _, devuelto = self.orden('borra la nota de la boda', 'No encuentro esa nota.', traza=[vacia])
        self.assertFalse(devuelto)
        self.assertEqual((runtime.notas, runtime.lecturas), (0, []))

    def test_si_ordeno_borrar_y_dice_borrada_sin_mirar_se_arranca_en_la_lista(self):
        # «Socio bórrala…» -> «¡Oído cocina! Borrada de inmediato» y ninguna llamada (20/11).
        runtime, turn, devuelto = self.orden('Socio bórrala no te explicado lo que sabes hacer',
                                             '¡Oído cocina! Borrada de inmediato.')
        self.assertTrue(devuelto)
        # Se arranca en una lectura, no en un borrado a ciegas.
        self.assertEqual((runtime.lecturas, runtime.notas), (['note.list'], 0))
        self.assertIn('no se ha descartado ninguna nota', turn.messages[0]['content'])
        # Con la lista delante, si vuelve a cerrar sin descartar, se le arranca en el descarte.
        turn.trace.append(self.LISTA)
        recovery = self.agente_de(turn)
        self.assertTrue(recovery.before_completion(None, turn, dict(reply='Ya está borrada.', work=None)))
        self.assertEqual((runtime.notas, runtime.pedida), (1, 'note.mark'))
        # Y no se repite una tercera vez.
        self.assertEqual(runtime.lecturas, ['note.list'])

    def test_quitar_o_hablar_de_borrar_no_es_la_orden(self):
        for texto in ('quita esa nota de la pantalla', 'se pueden borrar las notas?', 'no borres nada'):
            runtime, _, devuelto = self.orden(texto, 'Hecho.', traza=[self.LISTA])
            self.assertFalse(devuelto, texto)

    def test_si_pide_un_documento_y_no_se_crea_se_arranca_en_crearlo(self):
        # 18/11, Qwen3.6 35B: «primero el PDF invéntate lo que sea» -> «¡Hecho! He creado un PDF…».
        casos = (('Venga por orden socio primero el PDF invéntate lo que sea', '¡Hecho! He creado un documento PDF.'),
                 ('hazme un excel con los gastos', 'Claro, aquí va la tabla: | a | b |'),
                 ('pásalo a word', 'Vale.'))
        for texto, respuesta in casos:
            runtime, turn, devuelto = self.orden(texto, respuesta, pedidos=('descargas',))
            self.assertTrue(devuelto, texto)
            self.assertEqual((runtime.notas, runtime.pedida), (1, 'document.create'))
            self.assertIn('document_create', turn.messages[0]['content'])

    def test_pedido_como_pregunta_o_dejado_para_luego_tambien_se_crea(self):
        # 18/11, Gemma 4 26B: «Puedes hacer un world bien currado…?» -> «Dame un segundo que lo redacto»
        # y nada hasta que Andrés dijo «Okey».
        casos = (('Puedes hacer un world bien currado de lo que sea? Una narración o lo que te venga en gusto',
                  'Me pides que me luzca. Te voy a escribir un relato corto. Dame un segundo que lo redacto.'),
                 ('me haces un excel con mis gastos?', 'Claro.'),
                 ('quiero el informe en PDF', 'Te lo preparo ahora mismo.'),
                 ('Y ahora un world con una historia como la de diablo 3', 'Vale, ¿de qué va?'))
        for texto, respuesta in casos:
            runtime, _, devuelto = self.orden(texto, respuesta, pedidos=('descargas',))
            self.assertTrue(devuelto, texto)
            self.assertEqual(runtime.pedida, 'document.create', texto)

    def test_preguntar_si_sabe_hacerlos_no_es_pedir_uno(self):
        for texto, respuesta in (('sabes hacer PDFs?', 'Sí, puedo crearlos.'),
                                 ('puedes hacer excels con gráficos?', 'Sí: dime cuál y te lo preparo.'),
                                 ('hello world en python', 'print("hello world")')):
            runtime, _, devuelto = self.orden(texto, respuesta, pedidos=('descargas',))
            self.assertFalse(devuelto and runtime.pedida == 'document.create', texto)

    def test_bajar_leer_o_hablar_de_un_pdf_no_es_crearlo(self):
        casos = (('bájame el pdf del manual', 'Te he preparado la tarjeta.'),
                 ('lee el pdf que bajamos', 'Dice que…'),
                 ('resume este pdf', 'Trata de…'),
                 ('qué es un pdf?', 'Un formato de documento.'),
                 ('ya puedes crear pdf excel y word', '¡Qué buena noticia!'))
        for texto, respuesta in casos:
            runtime, _, devuelto = self.orden(texto, respuesta, pedidos=('descargas',))
            self.assertFalse(devuelto and runtime.pedida == 'document.create', texto)
        hecho = [dict(tool='document.create', arguments={}, result={'id': 'd1'}, failed=False)]
        runtime, _, devuelto = self.orden('hazme un pdf', 'Hecho.', pedidos=('descargas',), traza=hecho)
        self.assertFalse(devuelto)
        self.assertEqual(runtime.notas, 0)

    def test_hablar_de_apuntar_no_es_una_orden(self):
        for texto in ('a okey, y notas tienes verdad?', 'me gusta apuntar cosas en papel', 'que notas tengo?'):
            runtime, _, devuelto = self.orden(texto, 'Sí, puedo llevar tus notas.')
            self.assertFalse(devuelto, texto)
            self.assertEqual(runtime.notas, 0)

    def test_hablar_de_las_notas_en_el_chat_no_se_devuelve(self):
        # «a okey, y notas tienes verdad?»: el selector pidió notas, la respuesta era
        # buena y la devolución la cambió por una contestación al aviso.
        self.assertFalse(self.chat('Sí, tengo la capacidad de gestionar notas. Puedo crear una si me lo pides.')[2])

    def test_si_la_nota_se_guardo_no_se_devuelve(self):
        traza = [dict(tool='note.save', arguments={}, result={'id': 'n1'}, failed=False)]
        self.assertFalse(self.chat('He apuntado la nota.', traza)[2])

    def test_con_alguna_llamada_hecha_no_se_toca(self):
        traza = [dict(tool='system.status', arguments={}, result={'cpu': {}}, failed=False)]
        self.assertFalse(self.cierre(traza=traza, respuesta='Va bien.')[2])

    def test_la_instruccion_ya_no_pide_anunciar(self):
        self.assertNotIn('anuncia brevemente', native.POLICY)
        self.assertIn('No anuncies una consulta sin hacerla', native.POLICY)


class SinTarjetaTest(SinLlamadaTest):
    LEIDO = (dict(tool='project.read', result={}),)

    def test_manda_a_una_tarjeta_que_no_existe_y_se_devuelve_una_vez(self):
        runtime, turn, devuelto, otra = self.cierre(pedidos=('proyecto',), traza=self.LEIDO,
            respuesta='Propongo añadir la línea. Por favor, aprueba este cambio en la tarjeta.')
        self.assertTrue(devuelto)
        self.assertIn('no hay ninguna abierta', turn.messages[0]['content'])
        self.assertFalse(otra())

    def test_si_propuso_el_cambio_o_solo_cuenta_lo_ya_aprobado_no(self):
        propuesto = self.LEIDO + (dict(tool='project.write', result=dict(status='pending_approval')),)
        for traza, respuesta in ((propuesto, 'He propuesto el cambio: apruébalo en la tarjeta.'),
                                 (self.LEIDO, 'Sí, lo aprobaste en la tarjeta y ya está escrito.'),
                                 (self.LEIDO, 'El fichero tiene dos funciones.')):
            with self.subTest(respuesta=respuesta):
                self.assertFalse(self.cierre(pedidos=('proyecto',), traza=traza, respuesta=respuesta)[2])

    # Hasta el 16/11 en el Chat no había tarjetas y esta regla no aplicaba. Ahora tiene la de
    # las descargas, y ese mismo día el 26B la anunció sin llamar a file_download.
    DICHO_EL_16_11 = ('Puedo proponer la descarga para que tú la apruebes. Como son archivos PDF, una vez que le '
                      'des al botón de la tarjeta que te aparecerá, HexOS se encargará de bajarlos a tu ordenador.')

    def test_en_el_chat_la_tarjeta_que_falta_es_la_de_una_descarga(self):
        runtime, turn, devuelto, otra = self.cierre(ventana='chat', pedidos=('descargas',),
                                                    respuesta=self.DICHO_EL_16_11)
        self.assertTrue(devuelto)
        self.assertIn('file_download', turn.messages[0]['content'])
        self.assertNotIn('project_write', turn.messages[0]['content'])
        self.assertFalse(otra())

    def test_en_el_chat_se_devuelve_con_el_grupo_de_descargas_declarado(self):
        runtime = Runtime()
        runtime.active_groups = ['notas']
        self.assertTrue(self.cierre(ventana='chat', pedidos=(), runtime=runtime,
                                    respuesta='Dale al botón de la tarjeta para bajarlo.')[2])
        self.assertEqual(runtime.active_groups, ['notas', 'descargas'])

    def test_en_el_chat_con_la_descarga_propuesta_o_explicando_la_tarjeta_no(self):
        propuesta = (dict(tool='file.download', result=dict(status='pending_approval')),)
        explicada = ('Cuando te dije "tarjeta", me refería a una notificación visual. HexOS genera una tarjeta '
                     'con un botón de Aprobar. Si no te ha salido nada, es que no he lanzado la orden todavía.')
        for traza, respuesta in ((propuesta, 'He propuesto la descarga: apruébala en la tarjeta.'),
                                 ((), explicada), ((), 'Ya lo aprobaste en la tarjeta y está descargado.'),
                                 ((), 'Te dejo los dos enlaces para que los abras.')):
            with self.subTest(respuesta=respuesta):
                self.assertFalse(self.cierre(ventana='chat', pedidos=('descargas',), traza=traza,
                                             respuesta=respuesta)[2])


class SinFicheroTest(unittest.TestCase):
    def cerrar(self, respuesta, traza=(), proyecto='motor', decidido=False):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-sin-fichero-')
        self.addCleanup(tmp.cleanup)
        agent = Agent(tmp.name, Runtime())
        agent.ventana, agent.proyecto = 'agente', proyecto
        turn = TurnState(text='procede', image=None, model_request='procede', transcript=None)
        turn.grupos_pedidos, turn.trace, turn.decidido_en_tarjeta = ['proyecto'], list(traza), decidido
        salida = dict(reply=respuesta, work=None)
        return turn, agent.runner.recovery.before_completion(None, turn, salida), \
            lambda: agent.runner.recovery.before_completion(None, turn, salida)

    LEIDO = (dict(tool='project.read', result={}),)

    def test_dice_haber_creado_un_fichero_sin_proponerlo(self):
        turn, devuelto, otra = self.cerrar('He creado el archivo `tools/time_tool.py` con la implementación.\n'
                                           '```python\n' + 'x = 1\n' * 8 + '```', traza=self.LEIDO)
        self.assertTrue(devuelto)
        self.assertIn('no hay fichero ni tarjeta', turn.messages[0]['content'])
        self.assertFalse(otra())

    def test_el_fichero_entregado_en_el_chat_se_devuelve_para_que_lo_proponga(self):
        fichero = 'Lo he rediseñado desde cero.\n```python\n' + 'boton = 1\n' * 40 + '```\nDime qué tal.'
        turn, devuelto, otra = self.cerrar(fichero, traza=self.LEIDO)
        self.assertTrue(devuelto)
        self.assertIn('project_write', turn.messages[0]['content'])
        self.assertFalse(otra())
        propuesto = (dict(tool='project.write', result=dict(status='pending_approval')),)
        trozo = 'La función es esta:\n```python\n' + 'x = 1\n' * 8 + '```'
        for respuesta, traza, proyecto in ((fichero, propuesto, 'motor'), (trozo, self.LEIDO, 'motor'),
                                           (fichero, self.LEIDO, None)):
            with self.subTest(proyecto=proyecto, largo=len(respuesta), traza=len(traza)):
                self.assertFalse(self.cerrar(respuesta, traza=traza, proyecto=proyecto)[1])

    def test_no_salta_si_lo_propuso_si_ya_se_decidio_o_si_no_lo_afirma(self):
        propuesto = (dict(tool='project.write', result=dict(status='pending_approval')),)
        for argumentos in (dict(respuesta='He creado la propuesta del cambio.', traza=propuesto),
                           dict(respuesta='He creado el fichero y ya lo aprobaste.', traza=self.LEIDO, decidido=True),
                           dict(respuesta='He leído el fichero y he encontrado el fallo.', traza=self.LEIDO),
                           dict(respuesta='No he creado nada todavía.', traza=self.LEIDO),
                           dict(respuesta='He creado un plan en tres pasos.', proyecto=None, traza=self.LEIDO)):
            with self.subTest(respuesta=argumentos['respuesta']):
                self.assertFalse(self.cerrar(**argumentos)[1])


if __name__ == '__main__':
    unittest.main()
