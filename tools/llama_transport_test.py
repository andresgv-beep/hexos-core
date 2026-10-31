"""El puente con llama-server habla como Héctor, sin GPU."""
import unittest

from tools import llama_transport


class ResultadoTest(unittest.TestCase):
    def test_traduce_una_llamada_cortada_por_el_marcador(self):
        r = llama_transport.resultado(dict(content='<|tool_call>call:x{}<tool_call|>', stop_type='word', tokens_cached=120,
                                           timings=dict(prompt_n=20, predicted_n=10, prompt_ms=5, predicted_ms=7)))
        self.assertEqual(r['finish_reason'], 'stop')
        self.assertEqual(r['visible_text'], '<|tool_call>call:x{}<tool_call|>')
        self.assertEqual(r['usage'], dict(generated_tokens=10, prefill_tokens=20, prefill_reused=90))
        self.assertEqual(r['model_state']['cache_position'], 120)

    def test_fin_natural_y_limite(self):
        self.assertEqual(llama_transport.resultado(dict(stop_type='eos'))['finish_reason'], 'eos')
        self.assertEqual(llama_transport.resultado(dict(stop_type='limit'))['finish_reason'], 'max_tokens')

    def test_el_fin_de_turno_cuenta_como_fin_natural(self):
        r = llama_transport.resultado(dict(content='Hecho.', stop_type='word', stopping_word='<turn|>'))
        self.assertEqual(r['finish_reason'], 'eos')

    def test_quita_el_bos_y_separa_la_ranura_auxiliar(self):
        t = object.__new__(llama_transport.LlamaTransport)
        t.stop_tokens = ['<|tool_response>']
        cuerpos = []
        t.pedir = lambda cuerpo: cuerpos.append(cuerpo) or dict(content='hola', stop_type='eos')
        t.start('<bos>texto', None)
        self.assertEqual(t.finish()['visible_text'], 'hola')
        self.assertEqual((cuerpos[0]['prompt'], cuerpos[0]['id_slot'], cuerpos[0]['temperature']), ('texto', 0, 0))
        t.start('otro', None, True)
        t.finish()
        self.assertEqual(cuerpos[1]['id_slot'], 1)

    def test_no_admite_adjuntos(self):
        t = object.__new__(llama_transport.LlamaTransport)
        with self.assertRaisesRegex(RuntimeError, 'solo texto'):
            t.start('x', (b'', 1, 1))


if __name__ == '__main__':
    unittest.main()
