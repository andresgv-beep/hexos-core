"""Documentos que Helios crea: PDF, Word y Excel, su sitio en Descargas y su vista previa.

Sin red ni GPU; el PDF usa el Chrome del equipo y se salta si no hay. Sale del 18/11:
Andrés quiere que el Chat le haga un PDF, un Word o un Excel y verlo antes de bajarlo.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexos.agent import catalog, descargas, documentos
from hexos.agent.chat import Agent
from hexos.agent.chat_backend.history_archive import history_page
from hexos.agent.chat_backend.server import make_handler
from hexos.agent.chat_backend.verification import VerificationService
from hexos.agent.chat_backend.state import AgentDependencies

TEXTO = '''# Presupuesto de la reforma

Resumen para **Andrés**, con *precios orientativos*.

## Partidas

| Concepto | Unidades | Precio | Total |
|---|---|---|---|
| Azulejos | 24 | 18,50 € | 444,00 € |
| Mano de obra | 1 | 1.200 € | 1.200 € |
| Suma | | | =SUM(D2:D3) |
| Raro | | | =WEBSERVICE("http://x") |

- Plazo: dos semanas
- Pago en dos partes

<script>alert(1)</script>
'''
HAY_CHROME = any(shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'))


class Runtime:
    native = False

    def call(self, request):
        return {'ok': True}

    def generate(self, messages):
        return ''


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hexos-documentos-')
        self.casa = Path(self.tmp.name)
        entorno = mock.patch.dict(os.environ, {'HEXOS_DOWNLOADS_HOME': str(self.casa / 'bajado'),
                                               'HEXOS_DOCUMENTS_HOME': str(self.casa / 'documentos')})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.addCleanup(self.tmp.cleanup)
        self.agente = Agent(self.casa / 'ws', Runtime(), dependencies=AgentDependencies(
            nas_read=lambda *a, **k: None, web_search=lambda q, limit=5: {'items': []}, web_read=lambda u: {'text': 'x'}))

    def crear(self, formato, nombre='Presupuesto', contenido=TEXTO, **kw):
        with self.agente.store() as store:
            return documentos.crear(store, formato, nombre, contenido, **kw)


class Markdown(unittest.TestCase):
    def test_bloques(self):
        tipos = [b[0] for b in documentos.bloques(TEXTO)]
        self.assertEqual(tipos, ['titulo', 'parrafo', 'titulo', 'tabla', 'lista', 'parrafo'])
        tabla = documentos.bloques(TEXTO)[3][1]
        self.assertEqual(tabla[0], ['Concepto', 'Unidades', 'Precio', 'Total'])
        self.assertEqual(len(tabla), 5)

    def test_el_html_del_pdf_escapa_y_no_deja_guiones(self):
        pagina = documentos.a_html(TEXTO, 'x')
        self.assertNotIn('<script>', pagina)
        self.assertIn('&lt;script&gt;', pagina)
        self.assertIn("default-src 'none'", pagina)
        self.assertIn('<strong>Andrés</strong>', pagina)

    def test_celdas_de_excel(self):
        self.assertEqual(documentos.valor_celda('24'), (24, None))
        self.assertEqual(documentos.valor_celda('1.200'), (1200, None))
        self.assertEqual(documentos.valor_celda('18,50 €'), (18.5, '#,##0.00 €'))
        self.assertEqual(documentos.valor_celda('3.5'), (3.5, None))
        valor, formato = documentos.valor_celda('10%')
        self.assertAlmostEqual(valor, 0.1)
        self.assertEqual(formato, '0.##%')
        self.assertEqual(documentos.valor_celda('=SUM(B2:B5)'), ('=SUM(B2:B5)', None))
        # Lo que podría salir a la red o abrir algo al abrir el Excel se queda en texto.
        self.assertEqual(documentos.valor_celda('=WEBSERVICE("http://x")')[1], '@')
        self.assertEqual(documentos.valor_celda('=HYPERLINK("http://x")')[1], '@')
        self.assertEqual(documentos.valor_celda('Madrid'), ('Madrid', None))


class Crear(Base):
    def test_word(self):
        from docx import Document
        hecho = self.crear('word')
        self.assertEqual((hecho['name'], hecho['kind'], hecho['verified']), ('Presupuesto.docx', 'Word', True))
        documento = Document(str(self.casa / 'documentos' / 'Presupuesto.docx'))
        textos = [p.text for p in documento.paragraphs]
        self.assertIn('Presupuesto de la reforma', textos)
        self.assertEqual(documento.tables[0].cell(1, 0).text, 'Azulejos')

    def test_excel_una_hoja_por_tabla_con_numeros_y_formulas(self):
        from openpyxl import load_workbook
        hecho = self.crear('xlsx', 'Cuentas.xlsx')
        self.assertEqual(hecho['name'], 'Cuentas.xlsx')
        libro = load_workbook(self.casa / 'documentos' / 'Cuentas.xlsx')
        hoja = libro['Partidas']
        self.assertEqual(hoja['B2'].value, 24)
        self.assertEqual((hoja['C2'].value, hoja['C2'].number_format), (18.5, '#,##0.00 €'))
        self.assertEqual(hoja['D4'].value, '=SUM(D2:D3)')
        self.assertEqual(hoja['D5'].data_type, 's')
        self.assertEqual(hoja.freeze_panes, 'A2')

    def test_excel_sin_tablas_explica_como(self):
        with self.assertRaises(ValueError) as error:
            self.crear('xlsx', contenido='Solo texto')
        self.assertIn('al menos una tabla markdown', str(error.exception))

    @unittest.skipUnless(HAY_CHROME, 'sin Chrome en este equipo')
    def test_pdf_con_chrome(self):
        hecho = self.crear('pdf')
        datos = (self.casa / 'documentos' / 'Presupuesto.pdf').read_bytes()
        self.assertTrue(datos.startswith(b'%PDF'))
        self.assertEqual(hecho['bytes'], len(datos))

    def test_nombres_y_errores(self):
        self.crear('docx', '../../etc/passwd')
        self.assertTrue((self.casa / 'documentos' / 'etcpasswd.docx').is_file())
        segundo = self.crear('docx', '../../etc/passwd')
        self.assertEqual(segundo['name'], 'etcpasswd (2).docx')    # no se pisa nada
        with self.assertRaises(ValueError):
            self.crear('exe')
        with self.assertRaises(ValueError):
            self.crear('pdf', contenido='   ')

    def test_queda_en_descargas_y_como_documento(self):
        hecho = self.crear('docx')
        with self.agente.store() as store:
            fila = descargas.panel(store)['downloads'][0]
            self.assertEqual((fila['id'], fila['kind'], fila['source']), (hecho['id'], 'Word', 'hecho por Helios'))
            self.assertTrue(fila['preview'] and fila['viewable'] and fila['readable'])
            texto = store.db.execute('SELECT content FROM documents WHERE id=?', (hecho['document'],)).fetchone()[0]
            self.assertEqual(texto, TEXTO)
            self.assertEqual(descargas.listado(store)['downloads'][0]['source'], 'hecho por Helios')


# Lo que escribió el Qwen3.6 35B el 18/11 y salió como un Excel cojo, sin avisar.
DASHBOARD = """## Hoja 1: Seguimiento de Tareas Críticas

| ID | Módulo | Responsable | Estado Prioridad Fecha Límite % Completado Notas |
| :--- | :--- | :--- | :--- | ---:| ---:|
| MOD-01 Hector CUDA Kernels Andrés En Revisión Alta 30/11/2026 85% Optimización
MOD-02 HexOS API Endpoints Héctor Pendiente Media 15/12/2026 0% Esperando
"""
GASTOS = """## Gastos

Fecha | Concepto | Categoría | Importe
---|---|---|---
01/11 | Alquiler | Vivienda | 750,00 €
03/11 | Mercadona | Alimentación | 85,50 €
07/11 | Cena | Ocio | 65,00 €
15/11 | Cine | Ocio | 12,00 €
**Total** | | | =SUMA(D2:D5)
Ocio | | | =SUMAR.SI(C2:C5;"Ocio";D2:D5)

Gráfico: rosco

Recomendación: **gasta menos en ocio**.

- Revisar la luz
"""


class Mejoras(Base):
    """Lo que hace falta para que un Excel no sea humo (Andrés, 18/11)."""

    def test_una_tabla_que_no_cuadra_no_se_crea_y_dice_que_lineas_fallan(self):
        with self.assertRaises(ValueError) as error:
            self.crear('xlsx', 'Dashboard', DASHBOARD)
        aviso = str(error.exception)
        self.assertIn('línea 3: tiene 4 celdas', aviso)
        self.assertIn('línea 5: tiene 1 celdas', aviso)
        self.assertFalse((self.casa / 'documentos').exists() and any((self.casa / 'documentos').iterdir()))
        with self.assertRaises(ValueError):
            self.crear('pdf', 'Dashboard', DASHBOARD)        # tampoco un PDF cojo

    def test_filas_sin_los_bordes_valen(self):
        self.assertEqual(documentos.revisar(GASTOS, 'xlsx'), [])
        tabla = [b for b in documentos.bloques(GASTOS) if b[0] == 'tabla'][0][1]
        self.assertEqual(tabla[1], ['01/11', 'Alquiler', 'Vivienda', '750,00 €'])

    def test_formulas_en_espanol_calculadas_y_contadas_al_modelo(self):
        from openpyxl import load_workbook
        hecho = self.crear('xlsx', 'Gastos', GASTOS)
        hoja = load_workbook(self.casa / 'documentos' / 'Gastos.xlsx')['Gastos']
        self.assertEqual(hoja['D6'].value, '=SUM(D2:D5)')
        self.assertEqual(hoja['D7'].value, '=SUMIF(C2:C5,"Ocio",D2:D5)')
        formulas = hecho['contents']['formulas']
        self.assertEqual(formulas, ['D6 =SUM(D2:D5) = 912,50 €', 'D7 =SUMIF(C2:C5,"Ocio",D2:D5) = 77,00 €'])
        self.assertEqual(hoja['D6'].number_format, '#,##0.00 €')
        self.assertEqual(hecho['contents']['graficos'], ['rosco'])

    def test_el_texto_suelto_va_a_la_hoja_notas_y_el_grafico_al_excel(self):
        import zipfile
        from openpyxl import load_workbook
        self.crear('xlsx', 'Gastos', GASTOS)
        ruta = self.casa / 'documentos' / 'Gastos.xlsx'
        libro = load_workbook(ruta)
        self.assertEqual(libro.sheetnames, ['Gastos', 'Notas'])
        notas = [c.value for c in libro['Notas']['A']]
        self.assertEqual(notas, ['Recomendación: gasta menos en ocio.', '• Revisar la luz'])
        with zipfile.ZipFile(ruta) as z:
            grafico = [n for n in z.namelist() if n.startswith('xl/charts/')]
            self.assertTrue(grafico)
            self.assertIn(b'doughnutChart', z.read(grafico[0]))

    def test_el_pdf_dibuja_el_grafico_y_la_vista_previa_da_los_resultados(self):
        pagina = documentos.a_html(GASTOS, 'x')
        self.assertIn('<svg', pagina)
        self.assertIn('912,50', pagina)             # el total, calculado
        self.assertNotIn('=SUMA', pagina)
        fila = dict(name='Gastos.xlsx', content_type=documentos.FORMATOS['xlsx'][0])
        vista = documentos.vista(fila, GASTOS).decode()
        self.assertIn('912,50', vista)
        self.assertIn('Hoja: Notas', vista)
        self.assertIn('<svg', vista)

    def test_un_grafico_que_no_se_sabe_hacer_o_sin_numeros_se_dice(self):
        self.assertTrue(any('no lo sé hacer' in p for p in
                            documentos.revisar(GASTOS.replace('rosco', 'radar'), 'xlsx')))
        sin_numeros = '| a | b |\n|---|---|\n| x | y |\n| z | w |\n\nGráfico: barras\n'
        self.assertTrue(any('primera columna con nombres' in p for p in documentos.revisar(sin_numeros, 'xlsx')))

    def test_formulas_peligrosas_o_desconocidas_quedan_como_texto_y_se_avisa(self):
        texto = '| a | b |\n|---|---|\n| x | =WEBSERVICE("http://x") |\n| y | 2 |\n'
        hecho = self.crear('xlsx', 'Raro', texto)
        self.assertEqual(hecho['contents']['formulas_guardadas_como_texto'], ['=WEBSERVICE("http://x")'])

    def test_calculo(self):
        filas = [['n', 'v'], ['a', '2'], ['b', '3'], ['c', '=B2*B3+1'], ['d', '=SI(B4>5;"alto";"bajo")'],
                 ['e', '=REDONDEAR(B2/B3;2)'], ['f', '=B7+1'], ['g', '=B8']]
        calculado = documentos.calcular(filas)
        self.assertEqual(calculado[(2, 4)][0], 7.0)
        self.assertEqual(calculado[(2, 5)][0], 'alto')
        self.assertEqual(calculado[(2, 6)][0], 0.67)
        self.assertIsNotNone(calculado[(2, 7)][2])          # circular: error, no se cuelga


class GraficoPedido(Base):
    """18/11: pidió «un rosco», el 35B no escribió la línea «Gráfico:» y le contó que salía con una macro."""
    PEDIDO = """## Gastos Personales

| Categoría | Importe (€) | Porcentaje (%)
:---| ---:| ---:|
Alimentación | 350,00 € | 29%
Transporte | 150,00 € | 12%

**Total Mensual:** 500 €
"""

    def test_que_palabras_piden_un_grafico(self):
        casos = {'intenta crear un Excel con datos inventados sobre gastos y u rosco': 'rosco',
                 'con una tarta': 'tarta', 'pon una gráfica': 'barras', 'un gráfico de líneas': 'lineas',
                 'Hazme un PDF de una sola línea': None, 'un excel con columnas fecha e importe': None,
                 'hazme un excel de gastos': None}
        for mensaje, esperado in casos.items():
            self.assertEqual(documentos.grafico_pedido([mensaje]), esperado, mensaje)
        self.assertEqual(documentos.grafico_pedido(['Okey todo tuyo', 'un excel con un rosco']), 'rosco')

    def test_lo_pedido_en_la_conversacion_pone_el_grafico_aunque_el_modelo_lo_olvide(self):
        import zipfile
        with self.agente.store() as store:
            for rol, texto in (('user', 'intenta crear un Excel con datos inventados sobre gastos y u rosco'),
                               ('assistant', 'Voy.'), ('user', 'Okey todo tuyo')):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', (rol + texto, 'ts', rol, texto, texto))
            resultado = self.agente.dispatcher.dispatch(store, 'document.create',
                                                        dict(format='xlsx', name='Gastos', content=self.PEDIDO))
        self.assertEqual(resultado['contents']['graficos'], ['rosco'])
        with zipfile.ZipFile(self.casa / 'documentos' / 'Gastos.xlsx') as z:
            self.assertTrue(any(n.startswith('xl/charts/') for n in z.namelist()))

    def test_el_argumento_chart_y_sus_errores(self):
        hecho = self.crear('xlsx', 'Barras', self.PEDIDO, grafico='barras')
        self.assertEqual(hecho['contents']['graficos'], ['barras'])
        with self.assertRaises(ValueError):
            self.crear('xlsx', 'Raro', self.PEDIDO, grafico='radar')
        with self.assertRaises(ValueError):           # pedido a mano y sin tabla de números: que lo arregle
            self.crear('pdf', 'Texto', '| a | b |\n|---|---|\n| x | y |\n', grafico='rosco')

    def test_un_grafico_deducido_nunca_impide_crear(self):
        with self.agente.store() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             ('u1', 'ts', 'user', 'hazme un pdf con una gráfica', 'x'))
            resultado = self.agente.dispatcher.dispatch(store, 'document.create',
                                                        dict(format='pdf', name='Solo texto', content='# Hola\n\nNada más.'))
        self.assertEqual(resultado['status'], 'created')


# Lo que escribió el Gemma 4 26B el 18/11 y se rechazó once veces: datos, un resumen debajo con
# fórmulas que apuntan a la primera tabla, y el gráfico bajo el resumen.
GEMMA = """## Gastos Mensuales

| Categoría | Presupuesto | Gastado |
|---|---|---|
| Vivienda | 800 | 800 |
| Suministros | 150 | 175 |
| Supermercado | 400 | 380 |
| Ocio | 100 | 120 |

## Resumen

| Concepto | Valor |
|---|---|
| Total Presupuesto | =SUMA(B2:B5) |
| Total Gastado | =SUMA(C2:C5) |

Gráfico: rosco
"""


class UnaHoja(Base):
    def test_el_excel_de_gemma_sale_en_una_hoja_con_sus_totales_y_su_rosco(self):
        import zipfile
        from openpyxl import load_workbook
        hecho = self.crear('xlsx', 'Gastos', GEMMA)
        contenido = hecho['contents']
        self.assertEqual(contenido['formulas'], ['B9 =SUM(B2:B5) = 1.450', 'B10 =SUM(C2:C5) = 1.475'])
        self.assertEqual(contenido['graficos'], ['rosco'])
        self.assertEqual(contenido['hojas'], [dict(hoja='Gastos Mensuales', tablas=2, filas_de_datos=6,
                                                   graficos=['rosco'])])
        ruta = self.casa / 'documentos' / 'Gastos.xlsx'
        hoja = load_workbook(ruta)['Gastos Mensuales']
        self.assertEqual((hoja['A1'].value, hoja['A7'].value, hoja['A8'].value, hoja['B9'].value),
                         ('Categoría', 'Resumen', 'Concepto', '=SUM(B2:B5)'))
        with zipfile.ZipFile(ruta) as z:
            graficos = [n for n in z.namelist() if n.startswith('xl/charts/')]
            self.assertTrue(graficos)
            xml = z.read(graficos[0])
            self.assertIn(b"'Gastos Mensuales'!$B$2:$B$5", xml)    # los datos, no el resumen
            self.assertIn(b"'Gastos Mensuales'!$A$2:$A$5", xml)

    def test_sumar_sin_rango_en_la_fila_total(self):
        texto = '| Cosa | Importe |\n|---|---|\n| a | 10 € |\n| b | 5,50 € |\n| **Total** | =SUMA() |\n'
        hecho = self.crear('xlsx', 'Total', texto)
        self.assertEqual(hecho['contents']['formulas'], ['B4 =SUM(B2:B3) = 15,50 €'])

    def test_un_titulo_con_hoja_empieza_otra_hoja(self):
        from openpyxl import load_workbook
        texto = ('### Hoja 1: Tareas\n\n| Id | Hecho |\n|---|---|\n| a | 1 |\n\n'
                 '### Hoja 2: Métricas\n\n| Métrica | Valor |\n|---|---|\n| tps | 98 |\n')
        self.crear('xlsx', 'Dos', texto)
        self.assertEqual(load_workbook(self.casa / 'documentos' / 'Dos.xlsx').sheetnames, ['Tareas', 'Métricas'])

    def test_en_el_pdf_las_formulas_del_resumen_tambien_se_calculan(self):
        pagina = documentos.a_html(GEMMA, 'x')
        self.assertIn('1.450', pagina)
        self.assertIn('<svg', pagina)

    def test_tres_fallos_en_un_turno_y_para(self):
        roto = '| a | b |\n|---|---|\n| x |\n'
        with self.agente.store() as store:
            for _ in range(3):
                paso = dict(tool='document.create', arguments={}, result={'error': 'x'}, failed=True)
                store.db.execute('INSERT INTO tool_events (turn_id, ts, body) VALUES (?,?,?)', ('t1', 'ts', json.dumps(paso)))
            resultado = self.agente.dispatcher.dispatch(store, 'document.create',
                                                        dict(format='xlsx', name='x', content=roto), turn_id='t1')
        self.assertEqual(resultado['status'], 'stopped')
        self.assertIn('No lo intentes otra vez', resultado['error'])


RELATO = "[[matrix]]\n# La Caída del Ángel Oscuro\n\n## Capítulo I\n\n" + ("La ceniza caía como nieve negra. " * 80)


class QwenDel18(Base):
    """Lo que hizo el Qwen3.6 35B el 18/11 con «Y ahora un world con una historia como Diablo 3»."""

    def test_un_opcional_vacio_es_como_no_mandarlo(self):
        argumentos = dict(format='docx', name='x', content='# Hola', chart='')
        catalog.validate('document.create', argumentos)
        self.assertNotIn('chart', argumentos)
        with self.assertRaises(ValueError):          # uno obligatorio vacío sigue siendo un error
            catalog.validate('document.create', dict(format='docx', name='', content='# Hola'))

    def test_el_documento_pegado_en_el_chat_lo_crea_hexos(self):
        from hexos.agent.chat_backend.state import TurnState
        self.agente.ventana = 'chat'
        turno = TurnState(text='Y ahora un world con una historia como la de diablo 3 el videojuego a ver que sacas',
                          image=None, model_request='x', transcript=None)
        turno.grupos_pedidos = ['descargas']
        salida = dict(reply=RELATO, work=None)
        with self.agente.store() as store:
            otra = self.agente.runner.recovery.before_completion(store, turno, salida)
        self.assertFalse(otra)                        # sin otra generación de dos minutos
        self.assertIn('Word: «La Caída del Ángel Oscuro.docx»', salida['reply'])
        paso = turno.trace[-1]
        self.assertEqual((paso['tool'], paso['verification'], paso['result']['kind']), ('document.create', 'confirmada', 'Word'))
        from docx import Document
        textos = [p.text for p in Document(str(self.casa / 'documentos' / 'La Caída del Ángel Oscuro.docx')).paragraphs]
        self.assertEqual(textos[0], 'La Caída del Ángel Oscuro')
        self.assertNotIn('[[matrix]]', ' '.join(textos))

    def test_una_respuesta_corta_o_sin_pedir_documento_no_se_toca(self):
        from hexos.agent.chat_backend.state import TurnState
        self.agente.ventana = 'chat'
        for texto, respuesta in (('cuéntame una historia de diablo 3', RELATO),
                                 ('Y ahora un world con una historia', 'Vale, ¿de qué tema?'),
                                 ('esos por ejemplo la gente los imprime en papel y los guarda o simplemente los tienen en pdf?', RELATO),
                                 ('¿Cómo se crea un PDF?', 'Ya tienes un ejemplo. ' + RELATO),
                                 ('Quiero saber por qué los guardan en Excel.', RELATO)):
            turno = TurnState(text=texto, image=None, model_request='x', transcript=None)
            salida = dict(reply=respuesta, work=None)
            with self.agente.store() as store:
                with mock.patch.object(documentos, 'crear') as crear:
                    self.agente.runner.recovery.before_completion(store, turno, salida)
                    crear.assert_not_called()
            self.assertEqual(salida['reply'], respuesta)
            self.assertEqual(turno.trace, [])

    def test_intentos_rechazados_y_luego_bien_no_dan_aviso(self):
        from hexos.agent.chat_backend.verification import VerificationService
        fallo = dict(tool='document.create', failed=True, verification='no_cumplida', result={'error': 'x'})
        bien = dict(tool='document.create', failed=False, verification='confirmada', result={'id': 'a'})
        self.assertEqual(VerificationService.closure([fallo, fallo, bien])['reason'], 'comprobado')
        self.assertEqual(VerificationService.closure([bien, fallo])['reason'], 'parcial')


TRES_HOJAS = """## Hoja: Gastos
| Fecha | Concepto | Categoría | Importe |
|---|---|---|---|
| 05/01 | Alquiler | Vivienda | 850,00 € |
| 10/01 | Supermercado | Comida | 120,50 € |
| 05/02 | Alquiler | Vivienda | 850,00 € |
| 08/02 | Cine | Ocio | 29,50 € |

## Hoja: Resumen
| Categoría | Total |
|---|---|
| Vivienda | =SUMAR.SI(Gastos!C:C;"Vivienda";Gastos!D:D) |
| Comida | =SUMIF(gastos!C2:C5;"Comida";gastos!D2:D5) |
| Ocio | =SUMIF(Gastos!C:C;"Ocio";Gastos!D:D) |
| **TOTAL** | **=SUM(B2:B4)** |

## Hoja: Dashboard
| Categoría | % del total |
|---|---|
| Vivienda | =Resumen!B2/Resumen!B5 |
| Comida | =Resumen!B3/Resumen!$B$5 |
"""


class EntreHojas(Base):
    """El Excel que pidió Andrés el 18/11: el Resumen suma la hoja Gastos y el Dashboard divide
    entre el total del Resumen. Antes todas esas fórmulas quedaban como texto."""

    def test_las_formulas_de_otra_hoja_se_calculan_y_se_guardan_como_formulas(self):
        from openpyxl import load_workbook
        hecho = self.crear('xlsx', 'Tres', TRES_HOJAS)
        contenido = hecho['contents']
        self.assertNotIn('formulas_guardadas_como_texto', contenido)
        self.assertNotIn('formulas_con_error', contenido)
        self.assertEqual(contenido['formulas'], [
            'Resumen!B2 =SUMIF(Gastos!C:C,"Vivienda",Gastos!D:D) = 1.700,00 €',
            'Resumen!B3 =SUMIF(Gastos!C2:C5,"Comida",Gastos!D2:D5) = 120,50 €',
            'Resumen!B4 =SUMIF(Gastos!C:C,"Ocio",Gastos!D:D) = 29,50 €',
            'Resumen!B5 =SUM(B2:B4) = 1.850,00 €',
            'Dashboard!B2 =Resumen!B2/Resumen!B5 = 91,9 %',
            'Dashboard!B3 =Resumen!B3/Resumen!$B$5 = 6,5 %'])
        libro = load_workbook(self.casa / 'documentos' / 'Tres.xlsx')
        celda = libro['Resumen']['B2']
        self.assertEqual((celda.value, celda.data_type), ('=SUMIF(Gastos!C:C,"Vivienda",Gastos!D:D)', 'f'))
        self.assertEqual(libro['Dashboard']['B2'].number_format, '0.##%')

    def test_una_hoja_con_espacios_va_entre_comillas_y_una_que_no_existe_es_error(self):
        texto = ('## Hoja: Mis gastos\n| Cosa | Importe |\n|---|---|\n| a | 10 |\n| b | 5 |\n\n'
                 "## Hoja: Total\n| Qué | Cuánto |\n|---|---|\n| suma | =SUM('MIS GASTOS'!B2:B3) |\n"
                 '| otra | =Ventas!B2 |\n')
        contenido = documentos.resumen(texto, 'xlsx')
        self.assertEqual(contenido['formulas'], ["Total!B2 =SUM('Mis gastos'!B2:B3) = 15"])
        self.assertEqual(contenido['formulas_con_error'],
                         ['Total!B3 =VENTAS!B2 = error: no hay ninguna hoja que se llame «VENTAS»'])

    def test_otro_fichero_no_es_una_hoja(self):
        self.assertFalse(documentos.formula_segura("='[otro.xlsx]Hoja'!A1"))
        self.assertFalse(documentos.formula_segura('=[otro.xlsx]Hoja!A1'))
        self.assertTrue(documentos.formula_segura("='Mis gastos'!A1*2"))

    def test_la_tarta_va_al_resumen_por_categoria_y_no_a_los_gastos_sueltos(self):
        texto = documentos.con_grafico(TRES_HOJAS, 'tarta')
        hojas = {nombre: graficos for nombre, _, graficos in documentos.hojas(texto)}
        self.assertEqual(hojas, {'Gastos': [], 'Resumen': ['tarta'], 'Dashboard': []})
        lineas = documentos.con_grafico(TRES_HOJAS.replace('05/01', '05/01/2024'), 'lineas')
        self.assertEqual(documentos.hojas(lineas)[0][2], ['lineas'])     # sobre fechas, sí

    def test_los_totales_del_resumen_heredan_los_euros_de_lo_que_suman(self):
        contenido = documentos.resumen(TRES_HOJAS, 'xlsx')
        self.assertEqual(contenido['formulas'][:4], [
            'Resumen!B2 =SUMIF(Gastos!C:C,"Vivienda",Gastos!D:D) = 1.700,00 €',
            'Resumen!B3 =SUMIF(Gastos!C2:C5,"Comida",Gastos!D2:D5) = 120,50 €',
            'Resumen!B4 =SUMIF(Gastos!C:C,"Ocio",Gastos!D:D) = 29,50 €',
            'Resumen!B5 =SUM(B2:B4) = 1.850,00 €'])

    def test_una_formula_que_apunta_a_otra_aun_sin_calcular(self):
        calculado = documentos.calcular([['n', 'v'], ['a', '=B3+1'], ['b', '=2*3']])
        self.assertEqual(calculado[(2, 2)][0], 7.0)


class Herramienta(Base):
    def test_esta_en_el_chat_y_declara_sus_verbos(self):
        self.assertEqual(catalog.group_of('document.create'), 'descargas')
        self.assertIn('descargas', catalog.groups_in('chat'))
        self.assertTrue(catalog.TOOLS['document.create']['announces'])

    def test_el_despacho_crea_y_le_dice_al_modelo_que_no_pegue_el_contenido(self):
        with self.agente.store() as store:
            resultado = self.agente.dispatcher.dispatch(store, 'document.create',
                                                        dict(format='xlsx', name='Cuentas', content=TEXTO))
        self.assertEqual((resultado['status'], resultado['kind']), ('created', 'Excel'))
        self.assertIn('No le pegues el contenido', resultado['note'])
        # 18/11: sin `outcome` un PDF bien hecho salía como «Sin comprobar: document.create».
        with self.agente.store() as store:
            estado, _ = VerificationService(self.agente.env).verify(store, 'document.create', {}, resultado)
        self.assertEqual(estado, 'confirmada')

    def test_tras_recargar_la_respuesta_conserva_sus_documentos(self):
        with self.agente.store() as store:
            for rol, texto in (('user', 'hazme un excel'), ('assistant', 'Aquí lo tienes.'),
                               ('user', 'gracias'), ('assistant', 'De nada.')):
                store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)', (rol + texto, 'ts', rol, texto, texto))
            hecho = documentos.crear(store, 'xlsx', 'Cuentas', TEXTO)
            paso = dict(tool='document.create', arguments={}, result=dict(hecho, status='created'), failed=False)
            store.db.execute('INSERT INTO tool_events (turn_id, ts, body) VALUES (?,?,?)',
                             ('userhazme un excel', 'ts', json.dumps(paso)))
            store.db.commit()
            mensajes = history_page(store)['messages']
        self.assertEqual(mensajes[1]['documents'], [dict(id=hecho['id'], name='Cuentas.xlsx', kind='Excel',
                                                         bytes=hecho['bytes'])])
        self.assertNotIn('documents', mensajes[3])


class Servidor(Base):
    def setUp(self):
        super().setUp()
        ui = self.casa / 'ui.html'
        ui.write_text('x')
        self.servidor = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.agente, lambda: {},
                                                                           {'http://127.0.0.1:3000'}, ui))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.url = 'http://127.0.0.1:%d' % self.servidor.server_address[1]

    def bruto(self, ruta):
        try:
            with urllib.request.urlopen(self.url + ruta, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except HTTPError as error:
            with error:
                return error.code, dict(error.headers), error.read()

    def test_vista_previa_de_word_y_excel_sin_nada_ejecutable(self):
        for formato in ('docx', 'xlsx'):
            with self.subTest(formato):
                hecho = self.crear(formato)
                codigo, cabeceras, cuerpo = self.bruto(f'/api/downloads/{hecho["id"]}/preview')
                self.assertEqual(codigo, 200)
                self.assertIn('sandbox', cabeceras['Content-Security-Policy'])
                pagina = cuerpo.decode()
                self.assertIn('Azulejos', pagina)
                self.assertNotIn('<script>', pagina)
                codigo, cabeceras, cuerpo = self.bruto(f'/api/downloads/{hecho["id"]}/download')
                self.assertEqual(codigo, 200)
                self.assertIn('attachment', cabeceras['Content-Disposition'])
                self.assertTrue(cuerpo.startswith(b'PK'))

    def test_lo_bajado_de_la_web_no_tiene_vista_previa(self):
        with self.agente.store() as store:
            plan = descargas.mirar('https://example.com/x.docx',
                                   asomar=lambda u: (u, documentos.FORMATOS['docx'][0], 10))
            hecho = descargas.aplicar(store, plan, descargar=lambda u, l: (u, documentos.FORMATOS['docx'][0], b'PK..', False),
                                      pdf=lambda d, paginas, segundos: '')
            fila = store.db.execute('SELECT id FROM downloads WHERE name=?', (hecho['name'],)).fetchone()
        self.assertEqual(self.bruto(f'/api/downloads/{fila["id"]}/preview')[0], 404)

    def test_un_documento_movido_fuera_de_su_carpeta_no_se_sirve(self):
        hecho = self.crear('docx')
        fuera = self.casa / 'fuera.docx'
        (self.casa / 'documentos' / 'Presupuesto.docx').rename(fuera)
        with self.agente.store() as store:
            store.db.execute('UPDATE downloads SET path=? WHERE id=?', (str(fuera), hecho['id']))
            store.db.commit()
        self.assertEqual(self.bruto(f'/api/downloads/{hecho["id"]}/download')[0], 404)


if __name__ == '__main__':
    unittest.main()
