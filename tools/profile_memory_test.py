"""Guardar en el perfil solo lo que la persona acaba de decir, con su mensaje como evidencia."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent.chat import Agent
from hexos.agent.work import now


class FakeRuntime:
    def call(self, request): pass
    def generate(self, messages): return {'reply': '', 'work': None}


class FakeProfile:
    def __init__(self, confirmados=None):
        self.guardados = []
        self.corregidos = []
        self.confirmados = dict(confirmados or {})
    def read(self): return ''
    def keys(self): return dict(self.confirmados)
    def remember(self, key, value, text, evidence):
        self.guardados.append(dict(key=key, value=value, text=text, evidence=evidence))
        self.confirmados[key] = value
        return 'ok'
    def correct(self, key, value, text, evidence):
        self.corregidos.append(dict(key=key, value=value, text=text, evidence=evidence))
        self.confirmados[key] = value
        return 'ok'


class ProfileMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-perfil-test-')
        self.perfil = FakeProfile()
        self.agent = Agent(self.tmp.name, FakeRuntime(), self.perfil)

    def tearDown(self):
        self.tmp.cleanup()

    def turno(self, texto):
        uid = uuid4().hex
        with self.agent.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', texto, texto))
            store.db.commit()
        return uid

    def recordar(self, texto, key, value):
        uid = self.turno(texto)
        with self.agent.store() as store:
            return self.agent.remember_fact(store, dict(key=key, value=value), uid)

    def test_guarda_lo_que_la_persona_acaba_de_decir(self):
        resultado = self.recordar('hola, me llamo Andrés', 'nombre', 'Andrés')
        self.assertTrue(resultado['saved'])
        guardado = self.perfil.guardados[0]
        # HERA deriva el sujeto de la clave: sin «yo/» rechaza por sujeto_ajeno.
        self.assertEqual((guardado['key'], guardado['value']), ('yo/nombre', 'Andrés'))
        self.assertEqual(resultado['key'], 'yo/nombre')
        # La evidencia es su mensaje literal, no una cita que aporte el modelo.
        self.assertEqual(guardado['evidence'], 'hola, me llamo Andrés')
        self.assertEqual(resultado['source'], 'user_statement')

    def test_no_puede_confirmar_lo_que_deduce(self):
        with self.assertRaises(ValueError) as caught:
            self.recordar('¿te acuerdas de cómo me llamo?', 'nombre', 'Andrés')
        self.assertIn('no aparece en el mensaje', str(caught.exception))
        self.assertEqual(self.perfil.guardados, [])

    def test_sin_perfil_configurado_lo_dice_en_vez_de_fingir(self):
        agente = Agent(self.tmp.name, FakeRuntime())
        uid = self.turno('me llamo Andrés')
        with agente.store() as store:
            with self.assertRaises(ValueError) as caught:
                agente.remember_fact(store, dict(key='nombre', value='Andrés'), uid)
        self.assertIn('no se ha guardado', str(caught.exception))

    def test_sin_turno_no_hay_evidencia(self):
        with self.agent.store() as store:
            with self.assertRaises(ValueError):
                self.agent.remember_fact(store, dict(key='nombre', value='Andrés'), None)

    def test_la_etiqueta_no_admite_cualquier_cosa(self):
        for key in ('nombre; rm -rf /', '../../etc', 'a' * 61, ''):
            with self.assertRaises(ValueError):
                self.recordar('me llamo Andrés', key, 'Andrés')
        self.assertEqual(self.perfil.guardados, [])

    def test_la_etiqueta_se_normaliza_para_no_duplicar(self):
        self.recordar('me llamo Andrés', 'Nombre', 'Andrés')
        self.assertEqual(self.perfil.guardados[0]['key'], 'yo/nombre')

    def test_una_clave_con_sujeto_propio_se_respeta(self):
        self.recordar('mi gato se llama Turbo', 'gato/nombre', 'Turbo')
        self.assertEqual(self.perfil.guardados[0]['key'], 'gato/nombre')

    def test_un_dato_nuevo_se_guarda_y_uno_existente_se_corrige(self):
        self.recordar('me llamo Andrés', 'nombre', 'Andrés')
        self.assertEqual(len(self.perfil.guardados), 1)
        self.assertEqual(self.perfil.corregidos, [])
        # El mismo valor otra vez no toca nada.
        repetido = self.recordar('sigo siendo Andrés', 'nombre', 'Andrés')
        self.assertTrue(repetido['unchanged'])
        self.assertEqual(len(self.perfil.guardados), 1)
        # Un valor distinto corrige en vez de duplicar.
        cambio = self.recordar('en realidad me llamo Andrés García', 'nombre', 'Andrés García')
        self.assertTrue(cambio['corrected'])
        self.assertEqual(cambio['previous'], 'Andrés')
        self.assertEqual(self.perfil.corregidos[0]['key'], 'yo/nombre')
        self.assertEqual(len(self.perfil.guardados), 1, 'corregir no debe crear un segundo hecho')

    def test_un_rechazo_de_hera_no_se_reporta_como_guardado(self):
        # HERA rechaza con código 0 y "rechazado: <motivo>" en stdout.
        import subprocess
        from hexos.agent.continuity import HeraProfile
        perfil = HeraProfile('/bin/true', '/tmp')
        salida = subprocess.CompletedProcess([], 0, stdout='rechazado: sin_confirmacion\n', stderr='')
        with patch('hexos.agent.continuity.subprocess.run', return_value=salida):
            with self.assertRaises(ValueError) as caught:
                perfil.remember('nombre', 'Andrés', 'nombre: Andrés', 'me llamo Andrés')
        self.assertIn('sin_confirmacion', str(caught.exception))

    def test_la_frase_del_perfil_nombra_al_sujeto(self):
        # HERA imprime este texto tal cual en el perfil: si dos hechos de sujetos
        # distintos se redactan igual, el modelo lee un perfil que se contradice.
        self.recordar('mi hermana se llama Lucía', 'hermana/nombre', 'Lucía')
        self.recordar('mi ordenador se llama Rayo', 'ordenador/nombre', 'Rayo')
        self.recordar('me llamo Andrés', 'nombre', 'Andrés')
        self.recordar('mi coche tiene 200000 km', 'coche/kilometros', '200000')
        frases = [g['text'] for g in self.perfil.guardados]
        self.assertEqual(frases, ['Su hermana se llama Lucía',
                                  'Su ordenador se llama Rayo',
                                  'Su nombre es Andrés',
                                  'De su coche, kilometros: 200000'])
        self.assertEqual(len(set(frases)), len(frases))

    def test_el_catalogo_lo_declara_como_escritura(self):
        from hexos.agent import catalog
        spec = catalog.TOOLS['profile.remember']
        self.assertEqual(spec['effect'], 'write_profile')
        self.assertEqual(set(spec['required']), {'key', 'value'})
        # Sin esto el modelo pediría una cita en vez de dejar que HexOS la tome.
        self.assertIn('no aportes citas', spec['description'])

    def test_una_clave_con_espacios_se_lee_entera(self):
        # `hera lista` usa anchos fijos "%-5s %-11s %-28s %s". Partir por espacios
        # troceaba 'yo/coche nuevo' en clave 'yo/coche' y valor 'nuevo  Bruno', y
        # entonces un dato bien guardado parecía no estar.
        import subprocess
        from hexos.agent.continuity import HeraProfile
        salida = ('f19   confirmado  yo/coche nuevo               Bruno   [u91]\n'
                  'f18   confirmado  yo/nombre                    Andrés   [u90]\n')
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            self.assertEqual(perfil.keys(),
                             {'yo/coche nuevo': 'Bruno', 'yo/nombre': 'Andrés'})

    def test_la_salida_json_de_hera_se_lee_sin_columnas(self):
        # Cadenas escapadas: no hay ancho que desbordar ni separador que colisione.
        import json as _json, subprocess
        from hexos.agent.continuity import HeraProfile
        salida = _json.dumps(dict(count=2, truncated=False, facts=[
            dict(id='f19', state='confirmado', key='yo/coche nuevo', value='Bruno',
                 replaced_by='', evidence='u91'),
            dict(id='f20', state='candidato', key='yo/algo', value='sin confirmar',
                 replaced_by='', evidence='u92')]))
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            claves = perfil.keys()
        self.assertEqual(claves, {'yo/coche nuevo': 'Bruno'}, 'solo confirmados')
        self.assertEqual(perfil.unreadable, [])

    def test_una_fila_malformada_entre_buenas_no_se_traga_en_silencio(self):
        import json as _json, subprocess
        from hexos.agent.continuity import HeraProfile
        salida = _json.dumps(dict(count=3, truncated=False, facts=[
            dict(id='f1', state='confirmado', key='yo/nombre', value='Andrés'),
            dict(id='f2', state='confirmado', key=None, value='huérfano'),
            dict(id='f3', state='confirmado', key='yo/gato', value='Turbo')]))
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            claves = perfil.keys()
        self.assertEqual(claves, {'yo/nombre': 'Andrés', 'yo/gato': 'Turbo'})
        self.assertEqual(perfil.unreadable, ['f2'], 'la mala se declara, no se descarta')

    def test_una_lista_incompleta_se_declara_incompleta(self):
        # Con el cupo lleno no se puede concluir que algo no exista.
        import json as _json, subprocess
        from hexos.agent.continuity import HeraProfile
        salida = _json.dumps(dict(count=256, truncated=True, facts=[
            dict(id='f1', state='confirmado', key='yo/nombre', value='Andrés')]))
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            perfil.keys()
        self.assertTrue(perfil.unreadable)
        self.assertIn('incompleta', perfil.unreadable[0])

    def test_una_clave_desbordada_es_ilegible_no_inexistente(self):
        # El aviso que importa: saltarla evita leerla mal, pero no puede significar
        # «no existe» —eso haría guardar otra vez en vez de corregir.
        import subprocess
        from hexos.agent.continuity import HeraProfile
        larga = 'yo/' + 'x' * 40
        salida = ('f20   confirmado  ' + larga + ' Valor   [u92]\n'
                  'f18   confirmado  yo/nombre                    Andrés   [u90]\n')
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            claves = perfil.keys()
        self.assertEqual(claves, {'yo/nombre': 'Andrés'})
        self.assertEqual(perfil.unreadable, ['f20'], 'ilegible, y se dice cuál')

    def test_con_hechos_ilegibles_no_se_guarda_a_ciegas(self):
        class ConIlegibles(FakeProfile):
            unreadable = ['f20']
        perfil = ConIlegibles()
        agente = Agent(self.tmp.name, FakeRuntime(), perfil)
        uid = uuid4().hex
        with agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uid, now(), 'user', 'me llamo Andrés', 'me llamo Andrés'))
            store.db.commit()
            with self.assertRaises(ValueError) as caught:
                agente.remember_fact(store, dict(key='nombre', value='Andrés'), uid)
        self.assertIn('no duplicarlo', str(caught.exception))
        self.assertEqual(perfil.guardados, [])

    def test_una_clave_desbordada_se_salta_en_vez_de_leerse_mal(self):
        # Más de 28 caracteres: no hay forma de saber dónde acaba sin adivinar, y
        # leerla mal es peor que no leerla.
        import subprocess
        from hexos.agent.continuity import HeraProfile
        larga = 'yo/' + 'x' * 40
        salida = ('f20   confirmado  ' + larga + ' Valor   [u92]\n'
                  'f18   confirmado  yo/nombre                    Andrés   [u90]\n')
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            claves = perfil.keys()
        self.assertEqual(claves, {'yo/nombre': 'Andrés'})

    def test_hera_lista_se_parsea_con_sus_columnas(self):
        import subprocess
        from hexos.agent.continuity import HeraProfile
        salida = ('f3    confirmado  yo/nombre                    Andrés   [u71]\n'
                  'f4    confirmado  yo/gato                      Turbo  -> f9   [u80]\n'
                  'f1    candidato   legacy/algo suelto           x   [sin cita: legacy]\n')
        perfil = HeraProfile('/bin/true', '/tmp')
        with patch('hexos.agent.continuity.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, stdout=salida, stderr='')):
            claves = perfil.keys()
        # Solo confirmados, y el valor sin arrastrar la sustitución ni la cita.
        self.assertEqual(claves, {'yo/nombre': 'Andrés', 'yo/gato': 'Turbo'})

    def test_la_politica_no_nombra_la_herramienta(self):
        from hexos.agent.native import POLICY
        # La política NO debe nombrar la herramienta: el protocolo nativo parsea
        # la llamada del texto, así que mencionarla —aunque sea para prohibirla—
        # basta para que el modelo la emita y gaste una generación de más.
        self.assertNotIn('profile_remember', POLICY)
        self.assertIn('La memoria persistente la gestiona HexOS', POLICY)
        self.assertIn('sin confirmación', POLICY)
        self.assertNotIn('HexOS lo anota solo al cerrar el turno', POLICY)
        # Fase 3: consultar el perfil antes de preguntar un dato que ya consta.
        self.assertIn('Antes de preguntar un dato de la persona', POLICY)


if __name__ == '__main__':
    unittest.main()


class TratoTest(unittest.TestCase):
    """Cómo quiere que se le trate es un dato suyo, como su ciudad o su moto."""

    def test_sus_frases_reales_abren_el_porton(self):
        from hexos.agent.chat import AFIRMACION
        # Del 14/09/2026: ninguna de estas guardó nada, porque no pasaban el filtro.
        for texto in ('tambien me gustaria que seas un poco mas cercano como si fueras mi compañero',
                      'que lo recuerdes no que lo anotes',
                      'prefiero que me hables de tú',
                      'trátame como un compañero',
                      'no me hables así',
                      'no seas tan seco',
                      # Pedírselo con todas las letras, y un dato con número.
                      'memoriza que tengo dos hijos',
                      'guarda que mi taller está en el garaje',
                      'tengo dos hijos',
                      'tengo 3 gatos'):
            with self.subTest(texto):
                self.assertTrue(AFIRMACION.search(texto), texto)

    def test_la_conversación_de_trabajo_no_gasta_una_generación(self):
        from hexos.agent.chat import AFIRMACION
        for texto in ('revisa el nas', 'vale', 'qué contenedores hay', 'para el contenedor n8n',
                      'saca el listado de vecinos', 'gracias socio',
                      # «tengo un problema» no es un dato sobre él: por eso el
                      # patrón pide un número y no cualquier «tengo un…».
                      'tengo un problema con el nas', 'tengo una duda'):
            with self.subTest(texto):
                self.assertIsNone(AFIRMACION.search(texto), texto)


class TrazaDelPerfilTest(unittest.TestCase):
    """Lo que HexOS guarda en el perfil tiene que constar, o el propio cierre lo
    lee como una afirmación sin respaldo."""

    class Runtime:
        def call(self, request): pass
        def generate(self, messages): return {'reply': 'Listo.', 'work': None}
        def extract_facts(self, text): return [{'key': 'yo/trato', 'value': 'más cercano'}]

    def test_el_guardado_queda_en_la_traza_y_el_turno_cierra_comprobado(self):
        from hexos.agent.chat import Agent
        tmp = tempfile.TemporaryDirectory(prefix='hexos-traza-perfil-')
        self.addCleanup(tmp.cleanup)
        agent = Agent(tmp.name, self.Runtime())
        agent.profile = FakeProfile()
        r = agent.chat('me gustaría que seas más cercano')
        pasos = [t['tool'] for t in r['tools']]
        self.assertIn('profile.remember', pasos)
        paso = next(t for t in r['tools'] if t['tool'] == 'profile.remember')
        self.assertEqual(paso['effect'], 'write')
        self.assertEqual(paso['result']['requested_by'], 'hexos')
        # Y por tanto el turno no se cierra como «dice haber guardado y no consta».
        self.assertEqual(r['closure']['reason'], 'comprobado')
