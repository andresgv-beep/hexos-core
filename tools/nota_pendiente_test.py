"""«…te lo guardas en una nota:» sin el contenido: Helios espera, y lo siguiente es la nota."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import nota_pendiente
from hexos.agent.chat import Agent

ENCARGO = 'Mira, para que lo tengas claro y te lo guardas en una nota y lo marcas como favorito:'
CONTENIDO = 'En modo Agente puedes ejecutar programas, crear proyectos y pasarles pruebas.'


class Motor:
    """Devuelve lo que se le haya puesto en `pasos` y guarda lo que recibe."""
    def __init__(self, pasos):
        self.pasos, self.recibido = iter(pasos), []
    def call(self, request): pass
    def generate(self, messages):
        self.recibido.append(' '.join(m.get('content') or '' for m in messages))
        return next(self.pasos)


class FormaDelEncargoTest(unittest.TestCase):
    def test_pide_una_nota_y_acaba_en_dos_puntos(self):
        for texto in (ENCARGO, 'apunta esto:', 'Toma nota:', 'guárdame lo siguiente en notas:'):
            self.assertTrue(nota_pendiente.sin_contenido(texto), texto)
        # Con el contenido en el mismo mensaje, o sin pedir nota, no.
        for texto in ('anota: comprar pan', 'apunta que el viernes tengo dentista',
                      'te doy unas notas sobre el viaje:', 'mira lo que pone aquí:', '', 'x' * 290 + ' apunta esto:'):
            self.assertFalse(nota_pendiente.sin_contenido(texto), texto)
        self.assertTrue(nota_pendiente.encargo(ENCARGO)['anclar'])
        self.assertFalse(nota_pendiente.encargo('apunta esto:')['anclar'])


class EsperaElContenidoTest(unittest.TestCase):
    def agente(self, pasos):
        tmp = tempfile.TemporaryDirectory(prefix='hexos-nota-pendiente-'); self.addCleanup(tmp.cleanup)
        motor = Motor(pasos)
        agente = Agent(tmp.name, motor)
        agente.set_window('chat')
        return agente, motor

    def notas(self, agente):
        with agente.store() as store:
            return [dict(r) for r in store.db.execute('SELECT title, body, favorite FROM notes')]

    def test_aunque_el_modelo_intente_guardar_no_se_guarda_nada(self):
        # Lo del 20/11: no esperó y apuntó lo que tenía delante.
        agente, motor = self.agente([
            dict(tool='note.save', arguments=dict(title='Contexto Maestro', body='Lo que yo creo que quería decir')),
            dict(reply='Pásame lo que quieres que apunte.', work=None)])
        r = agente.chat(ENCARGO)
        self.assertEqual(self.notas(agente), [])
        paso = next(t for t in r['tools'] if t['tool'] == 'note.save')
        self.assertTrue(paso['failed'])
        self.assertIn('Todavía no ha dicho qué apuntar', paso['result']['error'])
        self.assertIn('NOTA SIN CONTENIDO', motor.recibido[0])
        self.assertTrue(agente.session.nota_pendiente['anclar'])

    def test_no_se_le_obliga_a_apuntar_mientras_falte_el_contenido(self):
        agente, motor = self.agente([dict(reply='Venga, dime qué apunto.', work=None)])
        r = agente.chat('apunta esto:')
        self.assertEqual(r['reply'], 'Venga, dime qué apunto.')
        self.assertEqual(len(motor.recibido), 1)          # no se le devolvió el turno
        self.assertEqual(self.notas(agente), [])

    def test_el_mensaje_siguiente_es_el_contenido_y_se_guarda_y_ancla(self):
        agente, motor = self.agente([
            dict(reply='Pásamelo.', work=None),
            dict(tool='note.save', arguments=dict(title='Lo que hago en Agente', body=CONTENIDO)),
            dict(reply='Apuntado.', work=None),
            dict(reply='Bien, gracias.', work=None)])
        agente.chat(ENCARGO)
        agente.chat(CONTENIDO)
        aviso = motor.recibido[1]
        self.assertIn('CONTENIDO DE LA NOTA', aviso)
        self.assertIn('ánclala con note_mark', aviso)
        self.assertEqual([(n['title'], n['body']) for n in self.notas(agente)], [('Lo que hago en Agente', CONTENIDO)])
        # De un solo uso: el tercer mensaje ya no es contenido de nada.
        self.assertIsNone(agente.session.nota_pendiente)
        agente.chat('¿qué tal?')
        self.assertNotIn('CONTENIDO DE LA NOTA', motor.recibido[-1])
        self.assertNotIn('NOTA SIN CONTENIDO', motor.recibido[-1])


if __name__ == '__main__':
    unittest.main()
