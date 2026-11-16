import unittest
from hexos.agent import qwen_protocol as q
from hexos.agent.native_transport import visible_preview

class Tests(unittest.TestCase):
    def test_calls(self):
        self.assertEqual(q.calls('<tool_call>{"name":"note_list","arguments":{}}</tool_call>'),
                         [dict(name='note_list', arguments={})])
        for value in ('{"name":"a","name":"b","arguments":{}}', '{"name":"a","arguments":null}'):
            with self.assertRaises(ValueError):q.calls('<tool_call>'+value+'</tool_call>')
        with self.assertRaises(ValueError):q.calls('<tool_call>{"name":"a","arguments":{}}</tool_call>extra')

    def test_size_arithmetic_is_folded_outside_strings(self):
        # La llamada literal que tumbó un turno: «Expecting ',' delimiter».
        raw = ('<tool_call>\n{"name": "nas_find", "arguments": {"device": "Synology", "extensions": '
               '["mkv", "mp4", "avi"], "min_bytes": 20 * 1024 * 1024 * 1024, '
               '"max_bytes": 40*1024*1024*1024}}\n</tool_call>')
        args = q.calls(raw)[0]['arguments']
        self.assertEqual((args['min_bytes'], args['max_bytes']), (20*1024**3, 40*1024**3))
        kept = q.calls('<tool_call>{"name":"a","arguments":{"query":"2 * 3 \\" 4*5","n":2*3}}</tool_call>')
        self.assertEqual(kept[0]['arguments'], {'query': '2 * 3 " 4*5', 'n': 6})
        for bad in ('"n":2*x', '"n":2**3', '"n":eval(1)'):
            with self.subTest(bad), self.assertRaises(ValueError):
                q.calls('<tool_call>{"name":"a","arguments":{' + bad + '}}</tool_call>')

    def test_results_and_thought(self):
        source = [dict(role='assistant', tool_calls=[], tool_responses=[
            dict(name='note_list',response={'total':2})])]
        rendered = q.render_messages(source)
        self.assertEqual(rendered[1]['role'], 'tool')
        self.assertIn('"total": 2', rendered[1]['content'])
        self.assertIn('tool_responses',source[0])
        self.assertEqual(q.split_thought('<think>private</think>Hola'), ('Hola','private'))
        self.assertEqual(visible_preview('<think>private'), '')
        self.assertEqual(visible_preview('<think>private</think>Hola'), 'Hola')


class CoderTest(unittest.TestCase):
    """Qwen3-Coder llama con etiquetas: <function=…> y <parameter=…>, con el valor en crudo."""
    TIPOS = {'project_write': {'path': 'str', 'content': 'str', 'old': 'str', 'new': 'str'},
             'project_read': {'path': 'str', 'start': 'int'},
             'project_run': {'command': 'list', 'timeout': 'int'},
             'nas_find': {'include_hidden': 'bool', 'extensions': 'list'}}

    def calls(self, text):
        return q.calls_xml(text, self.TIPOS.get)

    def una(self, nombre, cuerpo):
        return '<tool_call>\n<function=' + nombre + '>\n' + cuerpo + '</function>\n</tool_call>'

    def test_un_fichero_de_codigo_viaja_tal_cual(self):
        codigo = 'def f(a):\n    return "x" + a  # con \\n y {llaves}\n\nprint(f(\'b\'))'
        raw = self.una('project_write', '<parameter=path>\nsrc/main.py\n</parameter>\n'
                       '<parameter=content>\n' + codigo + '\n</parameter>\n')
        self.assertEqual(self.calls(raw), [dict(name='project_write', arguments=dict(path='src/main.py', content=codigo))])

    def test_un_cierre_de_etiqueta_dentro_del_valor_no_lo_corta(self):
        codigo = 'CIERRE = "</parameter>"\nOTRO = "</tool_call>"\nprint(CIERRE)'
        raw = self.una('project_write', '<parameter=path>\na.py\n</parameter>\n<parameter=content>\n' + codigo + '\n</parameter>\n')
        self.assertEqual(self.calls(raw)[0]['arguments']['content'], codigo)

    def test_los_tipos_los_pone_el_catalogo(self):
        raw = (self.una('project_read', '<parameter=path>\nmain.py\n</parameter>\n<parameter=start>\n401\n</parameter>\n') + '\n' +
               self.una('project_run', '<parameter=command>\n["python3", "-m", "unittest"]\n</parameter>\n<parameter=timeout>\n5\n</parameter>\n') + '\n' +
               self.una('nas_find', '<parameter=include_hidden>\nTrue\n</parameter>\n<parameter=extensions>\nmkv\nmp4\n</parameter>\n'))
        self.assertEqual(self.calls(raw), [
            dict(name='project_read', arguments=dict(path='main.py', start=401)),
            dict(name='project_run', arguments=dict(command=['python3', '-m', 'unittest'], timeout=5)),
            dict(name='nas_find', arguments=dict(include_hidden=True, extensions=['mkv', 'mp4']))])

    def test_sin_argumentos_y_herramienta_que_el_catalogo_no_conoce(self):
        self.assertEqual(self.calls(self.una('note_list', '')), [dict(name='note_list', arguments={})])
        self.assertEqual(self.calls(self.una('otra', '<parameter=n>\n3\n</parameter>\n'))[0]['arguments'], {'n': '3'})

    def test_lo_mal_formado_se_rechaza(self):
        buena = self.una('project_read', '<parameter=path>\na\n</parameter>\n')
        for mala, dice in ((buena + 'y algo más', 'inválida'),
                           ('<tool_call>\n<function=project_read>\n<parameter=path>\na\n</parameter>\n', 'incompleta'),
                           ('<tool_call>\n{"name": "a", "arguments": {}}\n</function>\n</tool_call>', 'sin <function'),
                           (self.una('project_read', '<parameter=path>\na\n</parameter>\n<parameter=path>\nb\n</parameter>\n'), 'duplicada'),
                           (self.una('project_read', 'texto suelto\n<parameter=path>\na\n</parameter>\n'), 'inesperado'),
                           (self.una('project_read', '<parameter=start>\ntres\n</parameter>\n'), 'número entero'),
                           (self.una('nas_find', '<parameter=include_hidden>\nquizá\n</parameter>\n'), 'true o false'),
                           (' '.join([buena] * 7), 'inválida')):
            with self.subTest(dice=dice), self.assertRaisesRegex(ValueError, dice):
                self.calls(mala)

    def test_el_adaptador_reconoce_la_plantilla_del_coder_y_conoce_los_tipos(self):
        from hexos.agent.native import NativeRuntime
        rt = NativeRuntime.__new__(NativeRuntime)
        rt.names = {'project_read': 'project.read'}
        self.assertEqual(rt.tipos_de_alias('project_read'), {'path': 'str', 'start': 'int'})
        self.assertIsNone(rt.tipos_de_alias('no_existe'))
