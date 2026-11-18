"""Documentos que Helios escribe para la persona: PDF, Word y Excel.

Helios escribe el contenido en markdown, como en el chat, y HexOS lo convierte. El PDF lo
imprime Chrome sin ventana a partir de un HTML propio; el Word sale de python-docx y el Excel
de openpyxl, una hoja por tabla. El fichero va a ~/Helios/documentos y aparece en Descargas,
donde se ve y se baja a cualquier dispositivo. Crear no pide aprobación: no sale a la red ni
toca nada del equipo fuera de esa carpeta.

Lo que se aprendió el 18/11 con los tres primeros Excel del Qwen3.6 35B, y que da forma a esto:

- **Escribe tablas mal formadas** (filas sin sus `|`, una tabla entera en una línea) y aquí se
  descartaban en silencio: un «dashboard» salió con la fila de títulos y nada más. Ahora una
  fila sin los `|` de los bordes vale, y una tabla que no cuadra no se crea: vuelve al modelo
  con las líneas malas para que la reescriba (`revisar`).
- **En un Excel se perdía todo lo que no era tabla.** Ahora va a una hoja «Notas».
- **Escribe las fórmulas en español** (`=SUMAR.SI(…;…)`) y calcula los totales de cabeza, mal.
  Ahora se traducen a las de Excel y se calculan aquí (`Calculo`) para la vista previa y para
  decirle al modelo los resultados de verdad.
- **Prometía gráficas que no existían.** Una línea `Gráfico: rosco` (tarta, barras, líneas)
  bajo una tabla la crea en el Excel y la dibuja en el PDF.
- **Contaba lo que pretendía, no lo que salió.** `crear` devuelve qué hay de verdad en el
  fichero (hojas, filas, fórmulas con su resultado, gráficas) para que describa solo eso.

Ver antes de bajar: el PDF lo enseña el navegador. Word y Excel no, así que `vista` rehace la
página desde el markdown guardado, con todo el texto escapado; el servidor la entrega con una
CSP que no deja ejecutar nada. Solo para documentos hechos aquí.
"""
from __future__ import annotations

import hashlib
import html
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from . import descargas
from .work import now

FORMATOS = {
    'pdf': ('application/pdf', '.pdf', 'PDF'),
    'docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx', 'Word'),
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx', 'Excel'),
}
ORIGEN = 'helios:documento'
MAX_CONTENIDO = 200_000
SEGUNDOS_PDF = 60
MAX_FILAS_VISTA = 500
NOTAS = 'Notas'

# Fórmulas que se dejan pasar a Excel: cuentas, nada que salga a la red ni abra ficheros
# (WEBSERVICE, HYPERLINK…). Lo demás que empiece por «=» se guarda como texto.
FUNCIONES = frozenset(('SUM', 'SUMIF', 'SUMIFS', 'AVERAGE', 'AVERAGEIF', 'COUNT', 'COUNTA', 'COUNTIF',
                       'COUNTIFS', 'MIN', 'MAX', 'ROUND', 'IF', 'IFERROR', 'ABS', 'PRODUCT', 'AND', 'OR'))
# El modelo y la persona escriben las fórmulas como en un Excel en español.
EN_ESPANOL = {'SUMA': 'SUM', 'SUMAR.SI': 'SUMIF', 'SUMAR.SI.CONJUNTO': 'SUMIFS', 'PROMEDIO': 'AVERAGE',
              'PROMEDIO.SI': 'AVERAGEIF', 'CONTAR': 'COUNT', 'CONTARA': 'COUNTA', 'CONTAR.SI': 'COUNTIF',
              'CONTAR.SI.CONJUNTO': 'COUNTIFS', 'REDONDEAR': 'ROUND', 'REDONDEO': 'ROUND', 'SI': 'IF',
              'SI.ERROR': 'IFERROR', 'PRODUCTO': 'PRODUCT', 'Y': 'AND', 'O': 'OR', 'MÁX': 'MAX', 'MÍN': 'MIN'}
GRAFICOS = {'rosco': 'rosco', 'rosquilla': 'rosco', 'anillo': 'rosco', 'anillos': 'rosco', 'donut': 'rosco',
            'tarta': 'tarta', 'circular': 'tarta', 'quesito': 'tarta', 'quesitos': 'tarta', 'pastel': 'tarta',
            'barras': 'barras', 'barra': 'barras', 'columnas': 'barras', 'lineas': 'lineas', 'líneas': 'lineas',
            'linea': 'lineas', 'línea': 'lineas'}
COLORES = ('#c9a24f', '#4f7fc9', '#5aa36a', '#c96a4f', '#8a6cc0', '#4fb3b3', '#c94f86', '#8c8c8c',
           '#d6c36b', '#6b8fd6')


def raiz():
    return Path(os.environ.get('HEXOS_DOCUMENTS_HOME') or Path.home() / 'Helios' / 'documentos').expanduser()


# --- Markdown, el que escribe el modelo --------------------------------------------------

_SEPARADOR = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')
_CERCA = re.compile(r'^\s*```')
_TITULO = re.compile(r'^(#{1,4})\s+(.*?)\s*#*\s*$')
_VINETA = re.compile(r'^\s*[-*+]\s+(.*)$')
_NUMERO = re.compile(r'^\s*\d+[.)]\s+(.*)$')
_GRAFICO = re.compile(r'^\s*(?:[*_]{1,2})?gr[aá]fic[oa]s?(?:[*_]{1,2})?\s*:\s*(?:[*_]{1,2})?\s*([\wáéíóú]+)', re.I)
_INLINE = re.compile(r'(\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|\*(?!\s)(.+?)(?<!\s)\*|(?<![\w])_(?!\s)(.+?)(?<!\s)_(?![\w]))')


def trozos(texto):
    """Una línea en trozos (texto, negrita, cursiva, código)."""
    salida, pos = [], 0
    for m in _INLINE.finditer(texto):
        if m.start() > pos:
            salida.append((texto[pos:m.start()], False, False, False))
        if m.group(2) or m.group(3):
            salida.append((m.group(2) or m.group(3), True, False, False))
        elif m.group(4):
            salida.append((m.group(4), False, False, True))
        else:
            salida.append((m.group(5) or m.group(6), False, True, False))
        pos = m.end()
    if pos < len(texto):
        salida.append((texto[pos:], False, False, False))
    return salida


def plano(texto):
    return ''.join(parte for parte, *_ in trozos(texto))


def _celdas(linea):
    linea = linea.strip()
    if linea.startswith('|'):
        linea = linea[1:]
    if linea.endswith('|'):
        linea = linea[:-1]
    return [c.strip() for c in linea.split('|')]


def _es_cabecera(lineas, n):
    return '|' in lineas[n] and n + 1 < len(lineas) and bool(_SEPARADOR.match(lineas[n + 1])) \
        and '-' in lineas[n + 1]


def _tablas(lineas):
    """Cada tabla con su línea de inicio (desde 1), sus columnas según el separador y sus filas
    con el número de línea de cada una. Una fila vale sin los `|` de los bordes."""
    salida, n, en_codigo = [], 0, False
    while n < len(lineas):
        if _CERCA.match(lineas[n]):
            en_codigo = not en_codigo
        elif not en_codigo and _es_cabecera(lineas, n):
            columnas = len(_celdas(lineas[n + 1]))
            filas = [(n + 1, _celdas(lineas[n]))]
            k = n + 2
            while k < len(lineas) and '|' in lineas[k] and lineas[k].strip() and not _es_cabecera(lineas, k):
                filas.append((k + 1, _celdas(lineas[k])))
                k += 1
            salida.append(dict(inicio=n + 1, columnas=columnas, filas=filas, fin=k))
            n = k
            continue
        n += 1
    return salida


def bloques(texto):
    """El markdown en bloques: titulo, parrafo, lista, numerada, codigo, cita, tabla, grafico, raya."""
    lineas = texto.replace('\r\n', '\n').split('\n')
    tablas = {t['inicio'] - 1: t for t in _tablas(lineas)}
    salida, parrafo, n = [], [], 0

    def cerrar():
        if parrafo:
            salida.append(('parrafo', ' '.join(l.strip() for l in parrafo)))
            parrafo.clear()
    while n < len(lineas):
        linea = lineas[n]
        if _CERCA.match(linea):
            cerrar()
            codigo = []
            n += 1
            while n < len(lineas) and not _CERCA.match(lineas[n]):
                codigo.append(lineas[n])
                n += 1
            salida.append(('codigo', '\n'.join(codigo)))
        elif n in tablas:
            cerrar()
            tabla = tablas[n]
            filas = [celdas for _, celdas in tabla['filas']]
            ancho = max(len(f) for f in filas)
            salida.append(('tabla', [f + [''] * (ancho - len(f)) for f in filas]))
            n = tabla['fin']
            continue
        elif _GRAFICO.match(linea):
            cerrar()
            salida.append(('grafico', GRAFICOS.get(_GRAFICO.match(linea).group(1).lower(), _GRAFICO.match(linea).group(1))))
        elif _TITULO.match(linea):
            cerrar()
            m = _TITULO.match(linea)
            salida.append(('titulo', len(m.group(1)), m.group(2)))
        elif re.match(r'^\s*(-{3,}|\*{3,}|_{3,})\s*$', linea):
            cerrar()
            salida.append(('raya',))
        elif _VINETA.match(linea) or _NUMERO.match(linea):
            cerrar()
            tipo = 'lista' if _VINETA.match(linea) else 'numerada'
            patron = _VINETA if tipo == 'lista' else _NUMERO
            elementos = []
            while n < len(lineas) and patron.match(lineas[n]):
                elementos.append(patron.match(lineas[n]).group(1).strip())
                n += 1
            salida.append((tipo, elementos))
            continue
        elif linea.lstrip().startswith('>'):
            cerrar()
            cita = []
            while n < len(lineas) and lineas[n].lstrip().startswith('>'):
                cita.append(lineas[n].lstrip()[1:].strip())
                n += 1
            salida.append(('cita', ' '.join(cita)))
            continue
        elif not linea.strip():
            cerrar()
        else:
            parrafo.append(linea)
        n += 1
    cerrar()
    return salida


def _corta(linea, tope=90):
    linea = linea.strip()
    return linea if len(linea) <= tope else linea[:tope - 1] + '…'


def revisar(texto, formato):
    """Lo que impide hacer bien el documento, en palabras que el modelo puede corregir. Vacío si está bien."""
    lineas = texto.replace('\r\n', '\n').split('\n')
    tablas = _tablas(lineas)
    problemas, dentro = [], set()
    for tabla in tablas:
        dentro.update(range(tabla['inicio'], tabla['fin'] + 1))
        dentro.add(tabla['inicio'] + 1)
        malas = [(numero, len(celdas)) for numero, celdas in tabla['filas'] if len(celdas) != tabla['columnas']]
        for numero, cuantas in malas[:5]:
            problemas.append(f'línea {numero}: tiene {cuantas} celdas y la tabla que empieza en la línea '
                             f'{tabla["inicio"]} tiene {tabla["columnas"]} columnas: «{_corta(lineas[numero - 1])}»')
        if len(malas) > 5:
            problemas.append(f'y {len(malas) - 5} filas más de esa tabla con las columnas mal')
        if len(tabla['filas']) < 2:
            problemas.append(f'la tabla de la línea {tabla["inicio"]} no tiene ninguna fila de datos')
    en_codigo = False
    for numero, linea in enumerate(lineas, 1):
        if _CERCA.match(linea):
            en_codigo = not en_codigo
        elif not en_codigo and numero not in dentro and linea.count('|') >= 2:
            problemas.append(f'línea {numero}: parece una fila de tabla, pero no va debajo de una fila de títulos '
                             f'con su separador |---|: «{_corta(linea)}»')
    for bloque in bloques(texto):
        if bloque[0] == 'grafico' and bloque[1] not in GRAFICOS.values():
            problemas.append(f'«Gráfico: {bloque[1]}» no lo sé hacer: usa rosco, tarta, barras o lineas')
    if formato == 'xlsx' and not tablas:
        problemas.append('un Excel necesita al menos una tabla markdown')
    # Un gráfico solo frena si no hay NINGUNA tabla que dibujar: si la línea cayó bajo un resumen
    # sin números, va a la tabla de datos más cercana (libro). Rechazarlo hizo que el Gemma 4 26B
    # reescribiera el mismo Excel once veces el 18/11.
    pedido = any(b[0] == 'grafico' and b[1] in GRAFICOS.values() for b in bloques(texto))
    if not problemas and pedido and formato in ('xlsx', 'pdf') and not dibujable(texto):
        problemas.append('se pide un gráfico y ninguna tabla tiene una primera columna con nombres y otra con '
                         'números')
    return problemas[:12]


# --- Fórmulas: traducir, comprobar y calcular ---------------------------------------------

def traducir(formula):
    """Una fórmula escrita como en un Excel en español, a la de Excel: SUMAR.SI→SUMIF, «;»→«,»."""
    partes = re.split(r'("[^"]*")', formula)
    punto_y_coma = any(';' in p for i, p in enumerate(partes) if i % 2 == 0)
    salida = []
    for i, parte in enumerate(partes):
        if i % 2:
            salida.append(parte)
            continue
        parte = parte.upper()
        parte = re.sub(r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ.]*)\s*\(', lambda m: EN_ESPANOL.get(m.group(1), m.group(1)) + '(', parte)
        if punto_y_coma:
            parte = re.sub(r'(?<=\d),(?=\d)', '.', parte).replace(';', ',')
        salida.append(parte)
    return ''.join(salida)


# Otra hoja delante de una celda o rango: «Gastos!C:C», «'Mi resumen'!B2». Sin «[», «\\» ni «/»
# dentro de las comillas: así no cabe una referencia a otro fichero ([libro.xlsx]Hoja!A1).
_PREFIJO = r"(?:'(?:[^'\[\]\\/:*?]|'')+'|[^\W\d][\w.]*)!"


def formula_segura(formula):
    sin_textos = re.sub(_PREFIJO, '', re.sub(r'"[^"]*"', '""', formula))
    return (bool(re.match(r'^=[A-Z0-9:$+\-*/().,<>=&%^" ]+$', sin_textos))
            and set(re.findall(r'([A-Z][A-Z.]*)\(', sin_textos)) <= FUNCIONES)


_ENTERO_ES = re.compile(r'^-?\d{1,3}(\.\d{3})+$')
_DECIMAL_ES = re.compile(r'^-?\d{1,3}(\.\d{3})*,\d+$|^-?\d+,\d+$')
_PUNTO = re.compile(r'^-?\d+(\.\d+)?$')
_EN_INGLES = re.compile(r'^-?\d{1,3}(,\d{3})+(\.\d+)?$')


def valor_celda(texto):
    """El texto de una celda como lo querría Excel: número, porcentaje, euros, fórmula o texto."""
    crudo = plano(texto.strip())
    if crudo.startswith('='):
        formula = traducir(crudo)
        return (formula, None) if formula_segura(formula) else (crudo, '@')
    formato = None
    numero = crudo.replace(' ', ' ').strip()
    if numero.startswith('€'):
        numero, formato = numero[1:].strip(), '#,##0.00 €'
    if numero.endswith('€'):
        numero, formato = numero[:-1].strip(), '#,##0.00 €'
    elif numero.endswith('%'):
        numero, formato = numero[:-1].strip(), '0.##%'
    numero = numero.replace(' ', '')
    if _ENTERO_ES.match(numero):
        valor = float(numero.replace('.', ''))
    elif _DECIMAL_ES.match(numero):
        valor = float(numero.replace('.', '').replace(',', '.'))
    elif _PUNTO.match(numero):
        valor = float(numero)
    elif _EN_INGLES.match(numero):
        valor = float(numero.replace(',', ''))
    else:
        return crudo, None
    if formato == '0.##%':
        valor /= 100
    if valor.is_integer() and formato is None:
        valor = int(valor)
    return valor, formato


class ErrorFormula(ValueError):
    pass


_TOKEN = re.compile(r'\s*(?:(?P<num>\d+(?:\.\d+)?%?)|(?P<str>"[^"]*")'
                    r'|(?P<rango>(?:' + _PREFIJO + r')?\$?[A-Z]{1,3}\$?\d+:\$?[A-Z]{1,3}\$?\d+)'
                    r'|(?P<columnas>(?:' + _PREFIJO + r')?\$?[A-Z]{1,3}:\$?[A-Z]{1,3}(?![\w$]))'
                    r'|(?P<celda>(?:' + _PREFIJO + r')?\$?[A-Z]{1,3}\$?\d+)'
                    r'|(?P<fn>[A-Z][A-Z.]*)\(|(?P<op><>|<=|>=|[-+*/^&=<>(),]))')


def _columna(letras):
    n = 0
    for letra in letras:
        n = n * 26 + ord(letra) - 64
    return n


def _ref(texto):
    m = re.match(r'\$?([A-Z]{1,3})\$?(\d+)', texto)
    return _columna(m.group(1)), int(m.group(2))


def _es_numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _cumple(valor, criterio):
    m = re.match(r'^(<>|<=|>=|<|>|=)?(.*)$', str(criterio), re.S)
    op, objetivo = m.group(1) or '=', m.group(2)
    try:
        objetivo_n = float(objetivo.replace(',', '.'))
    except ValueError:
        objetivo_n = None
    if objetivo_n is not None and _es_numero(valor):
        a, b = float(valor), objetivo_n
    else:
        a, b = str(valor if valor is not None else '').casefold(), objetivo.casefold()
    return {'=': a == b, '<>': a != b, '<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[op]


class Calculo:
    """Calcula las fórmulas de una hoja para la vista previa y el resumen. No es Excel: solo
    las funciones de FUNCIONES, referencias a celdas (de esta hoja o de otra del libro) y aritmética.

    El 18/11 el Gemma 4 26B hizo el Excel que se pide siempre: Gastos, un Resumen con
    =SUMAR.SI(Gastos!C:C;"Vivienda";Gastos!D:D) y un Dashboard con =Resumen!B2/Resumen!B7. Aquí
    cada hoja se calculaba sola y el «!» no pasaba la comprobación, así que todas esas fórmulas
    se guardaron como texto y el Excel no tenía ni una que funcionara."""

    def __init__(self, rejilla, libro=None):
        self.rejilla = rejilla          # {(columna, fila): valor o '=fórmula'}
        self.libro = libro if libro is not None else {}     # nombre en minúsculas -> Calculo
        self.hechos, self.en_curso = {}, set()
        self.tokens, self.pos = [], 0

    def _hoja(self, texto):
        """(Calculo de la hoja, referencia sin la hoja) para «Hoja!A1» o «A1»."""
        if '!' not in texto:
            return self, texto
        nombre, resto = texto.rsplit('!', 1)
        if nombre.startswith("'"):
            nombre = nombre[1:-1].replace("''", "'")
        otra = self.libro.get(nombre.casefold())
        if otra is None:
            raise ErrorFormula(f'no hay ninguna hoja que se llame «{nombre}»')
        return otra, resto

    def valor(self, columna, fila):
        clave = (columna, fila)
        crudo = self.rejilla.get(clave)
        if not (isinstance(crudo, str) and crudo.startswith('=')):
            return crudo
        if clave in self.hechos:
            return self.hechos[clave]
        if clave in self.en_curso:
            raise ErrorFormula('referencia circular')
        self.en_curso.add(clave)
        try:
            resultado = self.evaluar(crudo)
        finally:
            self.en_curso.discard(clave)
        self.hechos[clave] = resultado
        return resultado

    def evaluar(self, formula):
        # Una celda que apunta a otra fórmula vuelve a entrar aquí a mitad de la primera: sin
        # guardar dónde iba, =B3+1 con B3 =2*3 daba 6.
        guardado = self.tokens, self.pos
        try:
            return self._evaluar(formula)
        finally:
            self.tokens, self.pos = guardado

    def _evaluar(self, formula):
        texto, pos, self.tokens = formula[1:], 0, []
        while pos < len(texto):
            if texto[pos].isspace():
                pos += 1
                continue
            m = _TOKEN.match(texto, pos)
            if not m or m.end() == pos:
                raise ErrorFormula('no se entiende')
            self.tokens.append((m.lastgroup, m.group(m.lastgroup)))
            pos = m.end()
        self.pos = 0
        resultado = self._comparar()
        if self.pos != len(self.tokens):
            raise ErrorFormula('sobra algo')
        return resultado

    def _mira(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _toma(self, esperado=None):
        tipo, texto = self._mira()
        if esperado is not None and texto != esperado:
            raise ErrorFormula(f'se esperaba {esperado}')
        self.pos += 1
        return tipo, texto

    def _comparar(self):
        izquierda = self._sumar()
        tipo, op = self._mira()
        if tipo == 'op' and op in ('=', '<>', '<', '>', '<=', '>='):
            self._toma()
            return _cumple(izquierda, op + str(self._sumar()))
        return izquierda

    def _num(self, v):
        if v is None or v == '':
            return 0.0
        if _es_numero(v) or isinstance(v, bool):
            return float(v)
        raise ErrorFormula('texto donde va un número')

    def _sumar(self):
        v = self._multiplicar()
        while self._mira()[1] in ('+', '-', '&'):
            op = self._toma()[1]
            d = self._multiplicar()
            v = (str(v) + str(d)) if op == '&' else (self._num(v) + self._num(d) if op == '+' else self._num(v) - self._num(d))
        return v

    def _multiplicar(self):
        v = self._potencia()
        while self._mira()[1] in ('*', '/'):
            op = self._toma()[1]
            d = self._num(self._potencia())
            if op == '/' and d == 0:
                raise ErrorFormula('división por cero')
            v = self._num(v) * d if op == '*' else self._num(v) / d
        return v

    def _potencia(self):
        v = self._unario()
        if self._mira()[1] == '^':
            self._toma()
            v = self._num(v) ** self._num(self._unario())
        return v

    def _unario(self):
        if self._mira()[1] == '-':
            self._toma()
            return -self._num(self._unario())
        if self._mira()[1] == '+':
            self._toma()
        return self._primario()

    def _primario(self):
        tipo, texto = self._toma()
        if tipo == 'num':
            return float(texto[:-1]) / 100 if texto.endswith('%') else float(texto)
        if tipo == 'str':
            return texto[1:-1]
        if tipo == 'celda':
            hoja, ref = self._hoja(texto)
            return hoja.valor(*_ref(ref))
        if tipo == 'rango':
            hoja, ref = self._hoja(texto)
            return hoja._rango(ref)
        if tipo == 'columnas':
            hoja, ref = self._hoja(texto)
            return hoja._columnas(ref)
        if tipo == 'fn':
            argumentos = []
            if self._mira()[1] != ')':
                while True:
                    argumentos.append(self._comparar())
                    if self._mira()[1] == ',':
                        self._toma()
                        continue
                    break
            self._toma(')')
            return self._funcion(texto, argumentos)
        if texto == '(':
            v = self._comparar()
            self._toma(')')
            return v
        raise ErrorFormula('no se entiende')

    def _rango(self, texto):
        a, b = texto.split(':')
        (c1, f1), (c2, f2) = _ref(a), _ref(b)
        return [self.valor(c, f) for f in range(min(f1, f2), max(f1, f2) + 1)
                for c in range(min(c1, c2), max(c1, c2) + 1)]

    def _columnas(self, texto):
        """«C:C» o «C:D»: esas columnas enteras, de la fila 1 a la última que tenga algo."""
        a, b = (_columna(x.replace('$', '')) for x in texto.split(':'))
        ultima = max((f for (_, f) in self.rejilla), default=0)
        return [self.valor(c, f) for f in range(1, ultima + 1) for c in range(min(a, b), max(a, b) + 1)]

    @staticmethod
    def _plano(argumentos):
        for a in argumentos:
            yield from (a if isinstance(a, list) else [a])

    def _funcion(self, nombre, a):
        numeros = [float(v) for v in self._plano(a) if _es_numero(v)]
        if nombre == 'SUM':
            return sum(numeros)
        if nombre == 'PRODUCT':
            return math.prod(numeros) if numeros else 0.0
        if nombre in ('AVERAGE', 'MIN', 'MAX'):
            if not numeros:
                raise ErrorFormula('sin números')
            return {'AVERAGE': sum(numeros) / len(numeros), 'MIN': min(numeros), 'MAX': max(numeros)}[nombre]
        if nombre == 'COUNT':
            return float(len(numeros))
        if nombre == 'COUNTA':
            return float(sum(1 for v in self._plano(a) if v not in (None, '')))
        if nombre == 'ROUND':
            return round(self._num(a[0]), int(self._num(a[1])) if len(a) > 1 else 0)
        if nombre == 'ABS':
            return abs(self._num(a[0]))
        if nombre == 'IF':
            return a[1] if a[0] else (a[2] if len(a) > 2 else False)
        if nombre == 'IFERROR':
            return a[0]
        if nombre in ('AND', 'OR'):
            return (all if nombre == 'AND' else any)(bool(v) for v in self._plano(a))
        if nombre in ('SUMIF', 'COUNTIF', 'AVERAGEIF'):
            rango, criterio = a[0], a[1]
            suma = a[2] if len(a) > 2 else rango
            if not isinstance(rango, list) or not isinstance(suma, list):
                raise ErrorFormula('necesita rangos')
            elegidos = [s for r, s in zip(rango, suma) if _cumple(r, criterio)]
            if nombre == 'COUNTIF':
                return float(len(elegidos))
            elegidos = [float(v) for v in elegidos if _es_numero(v)]
            if nombre == 'SUMIF':
                return sum(elegidos)
            if not elegidos:
                raise ErrorFormula('sin números')
            return sum(elegidos) / len(elegidos)
        if nombre in ('SUMIFS', 'COUNTIFS'):
            suma = a[0] if nombre == 'SUMIFS' else None
            pares = a[1:] if nombre == 'SUMIFS' else a
            filas = len(pares[0]) if pares and isinstance(pares[0], list) else 0
            elegidas = [i for i in range(filas)
                        if all(isinstance(pares[k], list) and _cumple(pares[k][i], pares[k + 1])
                               for k in range(0, len(pares) - 1, 2))]
            if nombre == 'COUNTIFS':
                return float(len(elegidas))
            return sum(float(suma[i]) for i in elegidas if _es_numero(suma[i]))
        raise ErrorFormula(f'{nombre} no se calcula aquí')


def rejilla(filas):
    """Una tabla sola como hoja de Excel: títulos en la fila 1, datos desde la 2, columna A la primera."""
    celdas = {}
    for i, fila in enumerate(filas, 1):
        for j, texto in enumerate(fila, 1):
            celdas[(j, i)] = plano(texto) if i == 1 else valor_celda(texto)[0]
    return celdas


def _calcular_rejilla(celdas, calculo=None):
    calculo = calculo or Calculo(celdas)
    salida = {}
    for clave, crudo in celdas.items():
        if isinstance(crudo, str) and crudo.startswith('=') and formula_segura(crudo):
            try:
                salida[clave] = (calculo.valor(*clave), crudo, None)
            except (ErrorFormula, TypeError, ValueError, ZeroDivisionError, IndexError, OverflowError) as exc:
                salida[clave] = (None, crudo, str(exc) or 'error')
        else:
            salida[clave] = (crudo, None, None)
    return salida


def calcular(filas):
    """Cada celda de una tabla sola con su valor: {(columna, fila): (valor, fórmula o None, error o None)}."""
    return _calcular_rejilla(rejilla(filas))


def formato_columna(filas, columna):
    """El formato que llevan casi todos los datos de una columna (euros, %), para darle el mismo
    a sus fórmulas: un total de euros sin «€» no parecía un importe."""
    formatos = [valor_celda(f[columna - 1])[1] for f in filas[1:] if len(f) >= columna and f[columna - 1].strip()
                and not plano(f[columna - 1]).startswith('=')]
    for formato in ('#,##0.00 €', '0.##%'):
        if formatos and formatos.count(formato) * 2 >= len(formatos):
            return formato
    # Una columna toda de fórmulas no tiene datos de los que copiarlo: lo dice su título
    # («% del Total» daba 0,75 en vez de 75 %).
    if not formatos and len(filas[0]) >= columna:
        titulo = plano(filas[0][columna - 1])
        if '%' in titulo:
            return '0.##%'
        if '€' in titulo:
            return '#,##0.00 €'
    return None


def mostrar(valor, formato=None):
    if formato == '#,##0.00 €' and _es_numero(valor):
        return f'{valor:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.') + ' €'
    if formato == '0.##%' and _es_numero(valor):
        cifra = f'{valor * 100:.1f}'
        return (cifra[:-2] if cifra.endswith('.0') else cifra).replace('.', ',') + ' %'
    if isinstance(valor, bool):
        return 'VERDADERO' if valor else 'FALSO'
    if _es_numero(valor):
        if float(valor).is_integer():
            return f'{int(valor):,}'.replace(',', '.')
        return f'{valor:,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')
    return '' if valor is None else str(valor)


def _letra(columna):
    letras = ''
    while columna:
        columna, resto = divmod(columna - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _total(texto):
    return bool(re.match(r'^\W*(total|suma|subtotal|promedio|media)\b', plano(texto), re.I))


# --- El libro: cómo quedan las tablas en las hojas ---------------------------------------
#
# El 18/11 el Gemma 4 26B escribió una tabla de gastos y debajo un resumen con =SUMA(C2:C9):
# como cualquiera piensa un Excel, todo en una hoja. Aquí cada tabla iba a su hoja, así que
# esas fórmulas no apuntaban a nada; el gráfico, puesto bajo el resumen, no tenía números, y el
# documento se rechazó once veces seguidas. Ahora las tablas se apilan en la misma hoja, la
# primera con sus títulos en la fila 1, y solo un título con «Hoja» empieza otra.

_HOJA = re.compile(r'\bhoja\b', re.I)
_SIN_RANGO = re.compile(r'^=\s*(SUMA|SUM|PROMEDIO|AVERAGE|MAX|MIN|MÁX|MÍN|CONTAR|COUNT|CONTARA|COUNTA)\s*\(\s*\)\s*$', re.I)


def _rango_propio(texto, columna, fila0, filas):
    """«=SUMA()» en una celda: lo mismo sobre los datos de su columna hasta la primera fila de
    total. Así el modelo no tiene que adivinar en qué fila cae cada cosa."""
    m = _SIN_RANGO.match(plano(texto).strip())
    if not m:
        return None
    ultima = 0
    for i, fila in enumerate(filas[1:], 1):
        if _total(fila[0]):
            break
        ultima = i
    if not ultima:
        return None
    letra = _letra(columna)
    return f'={m.group(1)}({letra}{fila0 + 1}:{letra}{fila0 + ultima})'


def libro(texto):
    """Las hojas tal como quedan en el Excel, y con las que se calculan las fórmulas también en
    el PDF, el Word y la vista previa. Cada hoja: nombre, tablas (título, filas, fila de sus
    títulos, gráfico), celdas, formatos, filas de título y lo calculado."""
    hojas_, actual, pendiente = [], None, None

    def nueva(nombre):
        hoja = dict(nombre=nombre, tablas=[], celdas={}, formatos={}, titulos=[], siguiente=0)
        hojas_.append(hoja)
        return hoja
    for bloque in bloques(texto):
        tipo = bloque[0]
        if tipo == 'titulo':
            nombre = plano(bloque[2])
            if _HOJA.search(nombre):
                actual, pendiente = nueva(re.sub(r'^\s*hoja\s*\d*\s*[:.\-–—]?\s*', '', nombre, flags=re.I) or nombre), None
            else:
                pendiente = nombre
        elif tipo == 'tabla':
            filas = bloque[1]
            if actual is None:
                actual = nueva(pendiente)
            elif actual['nombre'] is None and not actual['tablas']:
                actual['nombre'] = pendiente
            if not actual['tablas']:
                fila0 = 1
                if actual['nombre'] is None:
                    actual['nombre'] = pendiente
            else:
                fila0 = actual['siguiente'] + 2
                if pendiente:
                    actual['celdas'][(1, fila0)] = pendiente
                    actual['titulos'].append(fila0)
                    fila0 += 1
            tabla = dict(titulo=pendiente, filas=filas, fila0=fila0, grafico=None, pedido=None)
            for i, fila in enumerate(filas):
                for j, texto_celda in enumerate(fila, 1):
                    clave = (j, fila0 + i)
                    if i == 0:
                        actual['celdas'][clave] = plano(texto_celda)
                        continue
                    propio = _rango_propio(texto_celda, j, fila0, filas)
                    valor, formato = (traducir(propio), None) if propio else valor_celda(texto_celda)
                    actual['celdas'][clave] = valor
                    if formato:
                        actual['formatos'][clave] = formato
                    elif isinstance(valor, str) and valor.startswith('='):
                        formato = formato_columna(filas, j)
                        if formato:
                            actual['formatos'][clave] = formato
            actual['tablas'].append(tabla)
            actual['siguiente'] = fila0 + len(filas) - 1
            pendiente = None
        elif tipo == 'grafico':
            if actual is not None and actual['tablas'] and actual['tablas'][-1]['pedido'] is None:
                actual['tablas'][-1]['pedido'] = bloque[1]
        else:
            pendiente = None
    # Las fórmulas que nombran otra hoja, con su nombre tal como queda en el Excel; y todas las
    # hojas calculadas juntas, para que el Resumen sume la hoja Gastos.
    nombres = _nombres(hojas_)
    reales = {n.casefold(): n for n in nombres}
    calculos = {}
    for nombre, hoja in zip(nombres, hojas_):
        for clave, valor in hoja['celdas'].items():
            if isinstance(valor, str) and valor.startswith('=') and '!' in valor:
                hoja['celdas'][clave] = _con_hojas(valor, reales)
        calculos[nombre.casefold()] = Calculo(hoja['celdas'], calculos)
    for nombre, hoja in zip(nombres, hojas_):
        hoja['calculado'] = _calcular_rejilla(hoja['celdas'], calculos[nombre.casefold()])
    _heredar_formatos(hojas_, nombres)
    # Cada gráfico, a una tabla que se pueda dibujar: la suya, o la más cercana de antes.
    todas = [(hoja, t) for hoja in hojas_ for t in hoja['tablas']]
    for indice, (hoja, tabla) in enumerate(todas):
        tipo = tabla['pedido']
        if not tipo or tipo not in GRAFICOS.values():
            continue
        candidatas = [todas[indice]] + todas[indice - 1::-1] + todas[indice + 1:] if indice else todas
        for otra_hoja, otra in candidatas:
            if otra['grafico'] is None and datos_grafico(otra_hoja, otra):
                otra['grafico'] = tipo
                break
    return hojas_


_REFERENCIA = re.compile(r'(?<![\w$.])(' + _PREFIJO + r')?(\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?'
                         r'|\$?[A-Z]{1,3}:\$?[A-Z]{1,3}(?![\w$]))')


def _heredar_formatos(hojas_, nombres):
    """Una fórmula sin formato toma el de las celdas que usa, si todas llevan el mismo: el
    =SUMAR.SI(Gastos!C:C;…;Gastos!D:D) de un Resumen sale en euros como la columna Importe, y su
    =SUMA(B2:B6) y su =B7/6 también. Un cociente entre dos celdas (un porcentaje) no hereda."""
    por_nombre = {n.casefold(): h for n, h in zip(nombres, hojas_)}
    for _ in range(4):                      # cadenas Gastos → Resumen → total → media
        cambio = False
        for hoja in hojas_:
            for clave, valor in hoja['celdas'].items():
                if clave in hoja['formatos'] or not (isinstance(valor, str) and valor.startswith('=')):
                    continue
                sin_textos = re.sub(r'"[^"]*"', '""', valor)
                referencias = _REFERENCIA.findall(sin_textos)
                if not referencias or ('/' in sin_textos and len(referencias) > 1):
                    continue
                formatos = set()
                for prefijo, ref in referencias:
                    nombre = prefijo[:-1].strip("'").replace("''", "'").casefold() if prefijo else None
                    otra = por_nombre.get(nombre) if nombre else hoja
                    if otra is None:
                        continue
                    a, _, b = ref.replace('$', '').partition(':')
                    if re.fullmatch(r'[A-Z]+', a):              # columnas enteras
                        columnas = range(_columna(a), _columna(b) + 1)
                        formatos.update(f for (j, i), f in otra['formatos'].items() if j in columnas and f != '@')
                    else:
                        (c1, f1), (c2, f2) = _ref(a), _ref(b or a)
                        formatos.update(f for (j, i), f in otra['formatos'].items()
                                        if c1 <= j <= c2 and f1 <= i <= f2 and f != '@')
                if len(formatos) == 1:
                    hoja['formatos'][clave] = formatos.pop()
                    cambio = True
        if not cambio:
            break


def _con_hojas(formula, reales):
    """«GASTOS!C:C» (traducir lo pasa a mayúsculas) como «Gastos!C:C», y entre comillas si el
    nombre lleva espacios: «'Gastos Mensuales'!C:C». Una hoja que no existe se deja: el cálculo
    lo dirá como error."""
    def poner(m):
        nombre = m.group(0)[:-1]
        if nombre.startswith("'"):
            nombre = nombre[1:-1].replace("''", "'")
        real = reales.get(nombre.casefold())
        if real is None:
            return m.group(0)
        return (real if re.fullmatch(r'[^\W\d][\w.]*', real) else "'" + real.replace("'", "''") + "'") + '!'
    partes = re.split(r'("[^"]*")', formula)
    return ''.join(p if i % 2 else re.sub(_PREFIJO, poner, p) for i, p in enumerate(partes))


def filas_grafico(tabla):
    """Las filas de datos de una tabla que entran en un gráfico (en la hoja): hasta la primera de total."""
    salida = []
    for i, fila in enumerate(tabla['filas'][1:], 1):
        if _total(fila[0]):
            break
        salida.append(tabla['fila0'] + i)
    return salida


def datos_grafico(hoja, tabla):
    """(columna de valores, nombre de la serie, [(etiqueta, valor)]) o None. Las etiquetas son la
    primera columna; los valores, la primera columna con números."""
    filas = filas_grafico(tabla)
    if len(filas) < 2:
        return None
    for columna in range(2, len(tabla['filas'][0]) + 1):
        valores = [hoja['calculado'].get((columna, f), (None,))[0] for f in filas]
        if sum(1 for v in valores if _es_numero(v)) * 2 >= len(valores):
            puntos = [(plano(str(hoja['calculado'].get((1, f), ('',))[0] or '')), float(v))
                      for f, v in zip(filas, valores) if _es_numero(v)]
            return columna, plano(tabla['filas'][0][columna - 1]), puntos
    return None


def hojas(texto):
    """Cada hoja del Excel: (nombre, número de tablas, gráficos)."""
    return [(h['nombre'], len(h['tablas']), [t['grafico'] for t in h['tablas'] if t['grafico']]) for h in libro(texto)]


def dibujable(texto):
    """Si alguna tabla del texto se puede dibujar: primera columna con nombres y otra con números."""
    return any(datos_grafico(h, t) for h in libro(texto) for t in h['tablas'])


def svg_grafico(tipo, serie, puntos, ancho=520):
    """El gráfico dibujado en SVG, para el PDF y la vista previa."""
    e = html.escape
    if tipo in ('rosco', 'tarta'):
        total = sum(max(0.0, v) for _, v in puntos) or 1.0
        alto = max(200, 26 + 22 * len(puntos))
        cx, cy, r = 110, alto / 2, 92
        partes, angulo = [], -math.pi / 2
        for i, (etiqueta, v) in enumerate(puntos):
            fraccion = max(0.0, v) / total
            if fraccion <= 0:
                continue
            fin = angulo + fraccion * 2 * math.pi
            if fraccion >= 0.9999:
                partes.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{COLORES[i % len(COLORES)]}"/>')
            else:
                x1, y1 = cx + r * math.cos(angulo), cy + r * math.sin(angulo)
                x2, y2 = cx + r * math.cos(fin), cy + r * math.sin(fin)
                grande = 1 if fin - angulo > math.pi else 0
                partes.append(f'<path d="M{cx},{cy} L{x1:.2f},{y1:.2f} A{r},{r} 0 {grande} 1 {x2:.2f},{y2:.2f} Z" '
                              f'fill="{COLORES[i % len(COLORES)]}" stroke="#fff" stroke-width="1.5"/>')
            angulo = fin
        if tipo == 'rosco':
            partes.append(f'<circle cx="{cx}" cy="{cy}" r="{r * 0.55}" fill="#fff"/>')
        leyenda = ''.join(
            f'<rect x="240" y="{14 + 22 * i}" width="12" height="12" rx="2" fill="{COLORES[i % len(COLORES)]}"/>'
            f'<text x="260" y="{24 + 22 * i}" font-size="12" fill="#333">{e(etiqueta[:34])} · '
            f'{e(mostrar(round(v, 2)))} ({max(0.0, v) / total:.0%})</text>' for i, (etiqueta, v) in enumerate(puntos))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%" '
                f'style="max-width:{ancho}px" role="img" aria-label="{e(serie)}">{"".join(partes)}{leyenda}</svg>')
    maximo = max([v for _, v in puntos] + [0.0]) or 1.0
    if tipo == 'lineas':
        alto, izquierda, base = 220, 50, 180
        paso = (ancho - izquierda - 20) / max(1, len(puntos) - 1)
        xy = [(izquierda + i * paso, base - (max(0.0, v) / maximo) * 150) for i, (_, v) in enumerate(puntos)]
        etiquetas = ''.join(f'<text x="{x:.1f}" y="{base + 16}" font-size="10" fill="#555" text-anchor="middle">'
                            f'{e(et[:12])}</text>' for (x, _), (et, _) in zip(xy, puntos))
        puntitos = ''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{COLORES[1]}"/>' for x, y in xy)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%" '
                f'style="max-width:{ancho}px" role="img" aria-label="{e(serie)}">'
                f'<line x1="{izquierda}" y1="{base}" x2="{ancho - 10}" y2="{base}" stroke="#bbb"/>'
                f'<polyline fill="none" stroke="{COLORES[1]}" stroke-width="2.5" '
                f'points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in xy)}"/>{puntitos}{etiquetas}'
                f'<text x="{izquierda}" y="14" font-size="11" fill="#555">{e(serie)} (máx. {e(mostrar(round(maximo, 2)))})</text></svg>')
    alto = 20 + 26 * len(puntos)
    barras = ''.join(
        f'<text x="0" y="{22 + 26 * i}" font-size="12" fill="#333">{e(et[:26])}</text>'
        f'<rect x="190" y="{10 + 26 * i}" width="{max(1.0, 250 * max(0.0, v) / maximo):.1f}" height="16" rx="2" '
        f'fill="{COLORES[i % len(COLORES)]}"/>'
        f'<text x="{196 + 250 * max(0.0, v) / maximo:.1f}" y="{22 + 26 * i}" font-size="11" fill="#555">'
        f'{e(mostrar(round(v, 2)))}</text>' for i, (et, v) in enumerate(puntos))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%" '
            f'style="max-width:{ancho}px" role="img" aria-label="{e(serie)}">{barras}</svg>')


def _svg_de(hoja, tabla):
    datos = datos_grafico(hoja, tabla) if tabla['grafico'] else None
    return ('<figure class="grafico">' + svg_grafico(tabla['grafico'], datos[1], datos[2]) + '</figure>') if datos else ''


# --- HTML: para el PDF y para la vista previa -------------------------------------------

def _html_trozos(texto):
    salida = []
    for parte, negrita, cursiva, codigo in trozos(texto):
        parte = html.escape(parte)
        if codigo:
            parte = f'<code>{parte}</code>'
        if negrita:
            parte = f'<strong>{parte}</strong>'
        if cursiva:
            parte = f'<em>{parte}</em>'
        salida.append(parte)
    return ''.join(salida)


def _tabla_html(hoja, tabla, maximo=None):
    cabecera, *datos = tabla['filas'][:maximo] if maximo else tabla['filas']
    cuerpo = []
    for i, fila in enumerate(datos, 1):
        celdas = []
        for j, texto in enumerate(fila, 1):
            clave = (j, tabla['fila0'] + i)
            valor, formula, error = hoja['calculado'].get(clave, (None, None, None))
            if formula:
                muestra = html.escape(f'#error ({error})' if error else mostrar(valor, hoja['formatos'].get(clave)))
                celdas.append(f'<td title="{html.escape(formula)}">{muestra}</td>')
            else:
                celdas.append(f'<td>{_html_trozos(texto)}</td>')
        cuerpo.append('<tr>' + ''.join(celdas) + '</tr>')
    return ('<div class="tabla"><table><thead><tr>' + ''.join(f'<th>{_html_trozos(c)}</th>' for c in cabecera)
            + '</tr></thead><tbody>' + ''.join(cuerpo) + '</tbody></table></div>')


def cuerpo_html(texto, graficos=True):
    """El documento como HTML. Las fórmulas salen calculadas y cada gráfico se dibuja bajo su tabla."""
    tablas = iter([(h, t) for h in libro(texto) for t in h['tablas']])
    partes = []
    for bloque in bloques(texto):
        tipo = bloque[0]
        if tipo == 'titulo':
            partes.append(f'<h{bloque[1]}>{_html_trozos(bloque[2])}</h{bloque[1]}>')
        elif tipo == 'parrafo':
            partes.append(f'<p>{_html_trozos(bloque[1])}</p>')
        elif tipo in ('lista', 'numerada'):
            etiqueta = 'ul' if tipo == 'lista' else 'ol'
            partes.append(f'<{etiqueta}>' + ''.join(f'<li>{_html_trozos(e)}</li>' for e in bloque[1]) + f'</{etiqueta}>')
        elif tipo == 'codigo':
            partes.append(f'<pre><code>{html.escape(bloque[1])}</code></pre>')
        elif tipo == 'cita':
            partes.append(f'<blockquote>{_html_trozos(bloque[1])}</blockquote>')
        elif tipo == 'tabla':
            hoja, tabla = next(tablas)
            partes.append(_tabla_html(hoja, tabla) + (_svg_de(hoja, tabla) if graficos else ''))
        elif tipo == 'raya':
            partes.append('<hr>')
    return '\n'.join(partes)


ESTILO_PDF = '''
@page { size: A4; margin: 18mm 17mm 20mm; }
body { font: 10.5pt/1.5 "Noto Sans", "DejaVu Sans", "Liberation Sans", sans-serif; color: #1d1d1f; }
h1 { font-size: 20pt; margin: 0 0 10pt; line-height: 1.2; }
h2 { font-size: 14.5pt; margin: 16pt 0 6pt; border-bottom: 1px solid #d9d6cf; padding-bottom: 3pt; }
h3 { font-size: 12pt; margin: 12pt 0 4pt; }
h4 { font-size: 10.5pt; margin: 10pt 0 3pt; }
p, ul, ol, blockquote, pre, table, figure { margin: 0 0 8pt; }
ul, ol { padding-left: 16pt; }
li { margin: 2pt 0; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; background: #f1efea; padding: 0 2pt; border-radius: 2pt; }
pre { background: #f6f4ef; border: 1px solid #e3e0d8; padding: 7pt 9pt; white-space: pre-wrap; border-radius: 3pt; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3pt solid #c9b27a; padding: 2pt 0 2pt 9pt; color: #4a4740; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; page-break-inside: auto; }
tr, figure { page-break-inside: avoid; }
th, td { border: 1px solid #d4d0c7; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #efece5; font-weight: 700; }
tr:nth-child(even) td { background: #faf9f6; }
hr { border: 0; border-top: 1px solid #d9d6cf; margin: 12pt 0; }
'''


def a_html(texto, titulo):
    # Sin red ni guiones: lo que Chrome imprime es solo este texto.
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            f'<title>{html.escape(titulo)}</title><style>{ESTILO_PDF}</style></head><body>'
            + cuerpo_html(texto) + '</body></html>')


def _chrome():
    for nombre in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    raise ValueError('No hay Chrome ni Chromium en este PC: sin él no se pueden hacer PDF.')


def hacer_pdf(texto, titulo, *, lanzar=subprocess.run):
    with tempfile.TemporaryDirectory(prefix='helios-pdf-') as tmp:
        fuente, salida = Path(tmp) / 'documento.html', Path(tmp) / 'documento.pdf'
        fuente.write_text(a_html(texto, titulo), encoding='utf-8')
        # Perfil propio y vacío: no toca el Chrome de la persona ni choca con él si está abierto.
        orden = [_chrome(), '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                 '--disable-extensions', '--disable-background-networking', '--disable-sync',
                 # Sin --blink-settings=scriptEnabled=false: con él Chrome no imprime nada. El HTML no
                 # lleva guiones y su CSP no dejaría correr ninguno.
                 f'--user-data-dir={tmp}/perfil',
                 '--no-pdf-header-footer', f'--print-to-pdf={salida}', fuente.as_uri()]
        try:
            lanzar(orden, capture_output=True, timeout=SEGUNDOS_PDF, check=False,
                   env=dict(os.environ, HOME=tmp))
        except subprocess.TimeoutExpired:
            raise ValueError(f'Chrome no terminó el PDF en {SEGUNDOS_PDF} s')
        if not salida.is_file() or not salida.read_bytes().startswith(b'%PDF'):
            raise ValueError('Chrome no generó el PDF')
        return salida.read_bytes()


# --- Word ---------------------------------------------------------------------------------

def _runs(parrafo, texto):
    from docx.shared import Pt
    for parte, negrita, cursiva, codigo in trozos(texto):
        run = parrafo.add_run(parte)
        run.bold, run.italic = negrita or None, cursiva or None
        if codigo:
            run.font.name = 'Consolas'
            run.font.size = Pt(9.5)


def hacer_docx(texto, titulo):
    import io
    from docx import Document
    from docx.shared import Pt
    tablas = iter([(h, t) for h in libro(texto) for t in h['tablas']])
    documento = Document()
    documento.core_properties.title = titulo
    documento.core_properties.author = 'Helios'
    normal = documento.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    for bloque in bloques(texto):
        tipo = bloque[0]
        if tipo == 'titulo':
            _runs(documento.add_heading(level=min(bloque[1], 4) if bloque[1] > 1 else 1), bloque[2])
        elif tipo == 'parrafo':
            _runs(documento.add_paragraph(), bloque[1])
        elif tipo in ('lista', 'numerada'):
            for elemento in bloque[1]:
                _runs(documento.add_paragraph(style='List Bullet' if tipo == 'lista' else 'List Number'), elemento)
        elif tipo == 'codigo':
            parrafo = documento.add_paragraph()
            run = parrafo.add_run(bloque[1])
            run.font.name = 'Consolas'
            run.font.size = Pt(9.5)
        elif tipo == 'cita':
            _runs(documento.add_paragraph(style='Quote'), bloque[1])
        elif tipo == 'tabla':
            hoja, info = next(tablas)
            filas = info['filas']
            tabla = documento.add_table(rows=len(filas), cols=len(filas[0]))
            tabla.style = 'Table Grid'
            for i, fila in enumerate(filas):
                for j, valor in enumerate(fila):
                    celda = tabla.cell(i, j)
                    celda.text = ''
                    clave = (j + 1, info['fila0'] + i)
                    resultado, formula, error = hoja['calculado'].get(clave, (None, None, None))
                    texto_celda = (('#error' if error else mostrar(resultado, hoja['formatos'].get(clave)))
                                   if formula and i else valor)
                    _runs(celda.paragraphs[0], texto_celda)
                    if i == 0 or (j == 0 and _total(fila[0])):
                        for run in celda.paragraphs[0].runs:
                            run.bold = True
            documento.add_paragraph()
        elif tipo == 'raya':
            documento.add_paragraph('—' * 20)
    salida = io.BytesIO()
    documento.save(salida)
    return salida.getvalue()


# --- Excel --------------------------------------------------------------------------------

def _nombre_hoja(propuesto, usados, n):
    nombre = re.sub(r'[\[\]:*?/\\|]', ' ', propuesto or f'Hoja {n}')
    nombre = re.sub(r'\s+', ' ', nombre).strip()[:31].strip() or f'Hoja {n}'
    base, k = nombre, 2
    while nombre.lower() in usados:
        sufijo = f' ({k})'
        nombre, k = base[:31 - len(sufijo)] + sufijo, k + 1
    usados.add(nombre.lower())
    return nombre


def _nombres(hojas_):
    usados = {NOTAS.lower()}
    return [_nombre_hoja(h['nombre'], usados, n) for n, h in enumerate(hojas_, 1)]


def _notas(texto):
    """Lo que no es tabla ni gráfico, en líneas para la hoja Notas. Los títulos que nombran una
    hoja o una tabla ya están en el Excel y no se repiten."""
    lista = bloques(texto)
    salida = []
    for i, bloque in enumerate(lista):
        tipo = bloque[0]
        if tipo == 'titulo':
            if _HOJA.search(plano(bloque[2])) or (i + 1 < len(lista) and lista[i + 1][0] == 'tabla'):
                continue
            salida.append((plano(bloque[2]), True))
        elif tipo in ('parrafo', 'cita'):
            salida.append((plano(bloque[1]), False))
        elif tipo in ('lista', 'numerada'):
            salida.extend(((('• ' if tipo == 'lista' else f'{n}. ') + plano(e)), False)
                          for n, e in enumerate(bloque[1], 1))
        elif tipo == 'codigo':
            salida.extend((linea, False) for linea in bloque[1].split('\n'))
    return salida


def hacer_xlsx(texto, titulo):
    import io
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, DoughnutChart, LineChart, PieChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.properties import CalcProperties
    hojas_ = libro(texto)
    if not hojas_:
        raise ValueError('Para un Excel escribe una o varias tablas markdown (| col | col | con su fila |---|---|).')
    excel = Workbook()
    excel.remove(excel.active)
    excel.properties.title, excel.properties.creator = titulo, 'Helios'
    # Que Excel y LibreOffice calculen las fórmulas al abrir: openpyxl no guarda resultados.
    excel.calculation = CalcProperties(fullCalcOnLoad=True)
    for nombre, info in zip(_nombres(hojas_), hojas_):
        hoja = excel.create_sheet(nombre)
        anchos = {}
        for (j, i), valor in info['celdas'].items():
            celda = hoja.cell(row=i, column=j, value=valor)
            formato = info['formatos'].get((j, i))
            if formato == '@':
                celda.data_type, celda.number_format = 's', '@'
            elif formato:
                celda.number_format = formato
            if (j, i) not in [(1, f) for f in info['titulos']]:
                anchos[j] = max(anchos.get(j, 0), len(str(valor)) if not str(valor).startswith('=') else 10)
        for fila in info['titulos']:
            hoja.cell(row=fila, column=1).font = Font(bold=True, size=12)
        maximo = 1
        for tabla in info['tablas']:
            ancho = len(tabla['filas'][0])
            maximo = max(maximo, ancho)
            for j in range(1, ancho + 1):
                celda = hoja.cell(row=tabla['fila0'], column=j)
                celda.font = Font(bold=True)
                celda.fill = PatternFill('solid', fgColor='EFECE5')
                celda.alignment = Alignment(vertical='center')
            for i, fila in enumerate(tabla['filas'][1:], 1):
                if _total(fila[0]):
                    for j in range(1, ancho + 1):
                        hoja.cell(row=tabla['fila0'] + i, column=j).font = Font(bold=True)
        for j, ancho in anchos.items():
            hoja.column_dimensions[get_column_letter(j)].width = min(60, max(8, ancho + 2))
        if len(info['tablas']) == 1:
            hoja.freeze_panes = 'A2'
        for tabla in info['tablas']:
            datos = datos_grafico(info, tabla) if tabla['grafico'] else None
            if not datos:
                continue
            columna, serie, _ = datos
            ultima = filas_grafico(tabla)[-1]
            clase = {'rosco': DoughnutChart, 'tarta': PieChart, 'barras': BarChart, 'lineas': LineChart}[tabla['grafico']]
            dibujo = clase()
            if tabla['grafico'] == 'barras':
                dibujo.type = 'col'
            if tabla['grafico'] == 'rosco':
                dibujo.holeSize = 55        # el de serie, 10, casi no se ve como rosco
            dibujo.title = tabla['titulo'] or info['nombre'] or serie
            dibujo.add_data(Reference(hoja, min_col=columna, min_row=tabla['fila0'], max_row=ultima), titles_from_data=True)
            dibujo.set_categories(Reference(hoja, min_col=1, min_row=tabla['fila0'] + 1, max_row=ultima))
            dibujo.height, dibujo.width = 9, 15
            hoja.add_chart(dibujo, f'{get_column_letter(maximo + 2)}{tabla["fila0"]}')
    notas = _notas(texto)
    if notas:
        hoja = excel.create_sheet(NOTAS)
        for i, (linea, negrita) in enumerate(notas, 1):
            celda = hoja.cell(row=i, column=1, value=linea)
            celda.alignment = Alignment(wrap_text=True, vertical='top')
            if negrita:
                celda.font = Font(bold=True, size=12)
        hoja.column_dimensions['A'].width = 100
    salida = io.BytesIO()
    excel.save(salida)
    return salida.getvalue()


# --- Lo que hay de verdad en el documento ------------------------------------------------

def resumen(texto, formato):
    """Qué contiene el fichero, para que el modelo lo cuente sin inventar."""
    hojas_ = libro(texto)
    formulas, como_texto, errores = [], [], []
    for nombre, hoja in zip(_nombres(hojas_), hojas_):
        for (j, i), (valor, formula, error) in sorted(hoja['calculado'].items(), key=lambda x: (x[0][1], x[0][0])):
            if formula:
                donde = f'{nombre}!{_letra(j)}{i}' if len(hojas_) > 1 else f'{_letra(j)}{i}'
                linea = f'{donde} {formula} = ' + (f'error: {error}' if error else mostrar(valor, hoja['formatos'].get((j, i))))
                (errores if error else formulas).append(linea)
            elif hoja['formatos'].get((j, i)) == '@':
                como_texto.append(str(valor))
    graficos = [t['grafico'] for h in hojas_ for t in h['tablas'] if t['grafico']]
    salida = dict(tablas=sum(len(h['tablas']) for h in hojas_), formulas=formulas[:12])
    if errores:
        salida['formulas_con_error'] = errores[:6]
    if como_texto:
        salida['formulas_guardadas_como_texto'] = como_texto[:5]
    if formato == 'xlsx':
        salida['hojas'] = [dict(hoja=n, tablas=len(h['tablas']),
                                filas_de_datos=sum(len(t['filas']) - 1 for t in h['tablas']),
                                graficos=[t['grafico'] for t in h['tablas'] if t['grafico']])
                           for n, h in zip(_nombres(hojas_), hojas_)]
        salida['hoja_notas'] = len(_notas(texto))
        salida['graficos'] = graficos
    elif formato == 'pdf':
        salida['graficos'] = graficos
    else:
        salida['graficos'] = []
        if any(t['pedido'] for h in hojas_ for t in h['tablas']):
            salida['aviso'] = 'Word no lleva gráficos: las líneas «Gráfico:» no salen en él'
    return salida


# --- El gráfico pedido --------------------------------------------------------------------

# «Una sola línea» o «con columnas de fecha e importe» no piden un gráfico: líneas y columnas
# solo cuentan detrás de «gráfico de».
_PIDE = ((re.compile(r'\b(?:roscos?|rosquillas?|donuts?|anillos?)\b', re.I), 'rosco'),
         (re.compile(r'\b(?:tartas?|quesitos?|gr[aá]fic[oa]s? circular(?:es)?)\b', re.I), 'tarta'),
         (re.compile(r'\b(?:barras|gr[aá]fic[oa]s? de columnas)\b', re.I), 'barras'),
         (re.compile(r'\bgr[aá]fic[oa]s? de (?:l[ií]neas|evoluci[oó]n)\b', re.I), 'lineas'),
         (re.compile(r'\bgr[aá]fic[oa]s?\b', re.I), 'barras'))


def grafico_pedido(mensajes):
    """El gráfico que la persona ha pedido en sus últimos mensajes, el más reciente primero, o None.
    El 18/11 el 35B no escribió la línea «Gráfico:» y contestó que el rosco salía con una macro."""
    for mensaje in mensajes:
        nombrado = [tipo for patron, tipo in _PIDE[:4] if patron.search(mensaje or '')]
        if nombrado:
            return nombrado[0]
        if _PIDE[4][0].search(mensaje or ''):
            return 'barras'
    return None


_FECHA = re.compile(r'^\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{1,4})?$')


def _por_categorias(puntos):
    """Si los puntos de un gráfico son categorías (pocas, sin repetir, no fechas)."""
    etiquetas = [e.strip().casefold() for e, _ in puntos]
    return (len(etiquetas) <= 12 and len(set(etiquetas)) == len(etiquetas)
            and not any(_FECHA.match(e) for e in etiquetas))


def con_grafico(texto, tipo):
    """El markdown con un «Gráfico: tipo» bajo la primera tabla que se pueda dibujar, si ninguna
    lleva ya el suyo. ValueError si no hay ninguna tabla con nombres y números."""
    tipo = GRAFICOS.get((tipo or '').strip().lower())
    if not tipo:
        raise ValueError('chart es rosco, tarta, barras o lineas')
    hojas_ = libro(texto)
    if any(t['grafico'] for h in hojas_ for t in h['tablas']):
        return texto
    lineas = texto.replace('\r\n', '\n').split('\n')
    tablas = _tablas(lineas)
    dibujables = [(posicion, datos_grafico(hoja, tabla)) for (hoja, tabla), posicion
                  in zip([(h, t) for h in hojas_ for t in h['tablas']], tablas)]
    dibujables = [(posicion, datos) for posicion, datos in dibujables if datos]
    # Una tarta, un rosco o unas barras van a la tabla por categorías, no a la de los datos
    # sueltos: el 18/11 la tarta salió sobre los 30 gastos, una porción por fecha, con el
    # Resumen por categoría dos hojas más allá. Las líneas sí van bien sobre fechas.
    if tipo != 'lineas':
        dibujables = [d for d in dibujables if _por_categorias(d[1][2])] or dibujables
    if dibujables:
        posicion = dibujables[0][0]
        return '\n'.join(lineas[:posicion['fin']] + ['', f'Gráfico: {tipo}', ''] + lineas[posicion['fin']:])
    raise ValueError(f'Se ha pedido un gráfico de {tipo} y ninguna tabla tiene una primera columna con nombres y '
                     'otra con números: añade esa tabla y vuelve a llamar a document_create.')


# --- Crear, registrar y enseñar ----------------------------------------------------------

def _nombre(nombre, extension):
    base = re.sub(r'[^\w .()+-]', '', (nombre or '').strip()).strip(' .')
    base = re.sub(r'\.(pdf|docx|xlsx|doc|xls)$', '', base, flags=re.I)[:80].strip() or 'documento'
    return base + extension


def crear(store, formato, nombre, contenido, *, grafico=None, pdf=None):
    """Hace el fichero, lo guarda en su carpeta y lo apunta en Descargas. `grafico` añade uno a la
    primera tabla que se pueda dibujar (Excel y PDF), si el texto no trae ya su línea «Gráfico:»."""
    formato = (formato or '').strip().lower().lstrip('.')
    formato = {'word': 'docx', 'doc': 'docx', 'excel': 'xlsx', 'xls': 'xlsx'}.get(formato, formato)
    if formato not in FORMATOS:
        raise ValueError('format es pdf, docx o xlsx')
    if not isinstance(contenido, str) or not contenido.strip():
        raise ValueError('content está vacío: escribe el documento entero en markdown')
    if len(contenido) > MAX_CONTENIDO:
        raise ValueError(f'content pasa de {MAX_CONTENIDO} caracteres')
    problemas = revisar(contenido, formato)
    if not problemas and grafico and formato in ('xlsx', 'pdf'):
        contenido = con_grafico(contenido, grafico)
    if problemas:
        # No se crea un documento cojo: el modelo lo reescribe con las líneas malas delante.
        raise ValueError('No he creado el documento: el markdown tiene errores. Corrígelos y llama otra vez a '
                         'document_create con el documento entero. Cada fila de una tabla lleva las mismas '
                         'celdas que su fila de títulos, separadas por |. ' + ' · '.join(problemas))
    tipo, extension, clase = FORMATOS[formato]
    fichero = _nombre(nombre, extension)
    titulo = fichero[:-len(extension)]
    if formato == 'pdf':
        datos = (pdf or hacer_pdf)(contenido, titulo)
    elif formato == 'docx':
        datos = hacer_docx(contenido, titulo)
    else:
        datos = hacer_xlsx(contenido, titulo)
    if len(datos) > descargas.MAX_BYTES:
        raise ValueError(f'el documento pasa de {descargas.tamano(descargas.MAX_BYTES)}')
    carpeta = raiz()
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = descargas._libre(carpeta / fichero)
    parcial = destino.with_name('.' + destino.name + '.parcial')
    with os.fdopen(os.open(parcial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644), 'wb') as salida:
        salida.write(datos)
    os.replace(parcial, destino)
    huella = hashlib.sha256(datos).hexdigest()
    # Lo escrito queda también como documento: Helios lo puede releer o retocar después, y la
    # vista previa se rehace desde aquí.
    documento = uuid4().hex
    store.db.execute('INSERT INTO documents VALUES (?,?,?,?)',
                     (documento, now(), contenido, hashlib.sha256(contenido.encode()).hexdigest()))
    descargas.initialize(store)
    identificador = uuid4().hex
    store.db.execute('INSERT INTO downloads VALUES (?,?,?,?,?,?,?,?,?)',
                     (identificador, now(), destino.name, str(destino), ORIGEN, tipo, len(datos), huella, documento))
    store.db.commit()
    comprobado = hashlib.sha256(destino.read_bytes()).hexdigest() == huella
    # `outcome` es lo que lee la comprobación del turno (verify='self'). Sin él, el 18/11 un
    # PDF bien hecho salió en el chat como «Sin comprobar: document.create».
    return dict(id=identificador, name=destino.name, kind=clase, format=formato, bytes=len(datos),
                size=descargas.tamano(len(datos)), folder=descargas._corta(carpeta), document=documento,
                contents=resumen(contenido, formato),
                verified=comprobado, outcome='hecho' if comprobado else 'no_se_sostuvo')


def es_suyo(fila):
    return fila['url'] == ORIGEN


def con_vista(fila):
    """Si «Ver» enseña una vista previa hecha aquí (Word y Excel de Helios)."""
    return es_suyo(fila) and fila['content_type'] in (FORMATOS['docx'][0], FORMATOS['xlsx'][0])


ESTILO_VISTA = '''
:root { color-scheme: light; }
body { margin: 0; background: #e9e7e2; font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1d1d1f; }
.aviso { position: sticky; top: 0; z-index: 1; background: #1d1d1f; color: #ece8df; padding: 8px 14px; font-size: 13px; }
.hoja { background: #fff; max-width: 860px; margin: 18px auto; padding: 32px 36px; box-shadow: 0 1px 4px rgba(0,0,0,.12); }
@media (max-width: 640px) { .hoja { margin: 0; padding: 18px 14px; box-shadow: none; } }
h1, h2, h3, h4 { line-height: 1.25; margin: 1.1em 0 .4em; } h1 { margin-top: 0; }
table { border-collapse: collapse; margin: 0 0 1em; font-size: 13px; }
th, td { border: 1px solid #d4d0c7; padding: 4px 8px; text-align: left; vertical-align: top; white-space: pre-wrap; }
th { background: #efece5; }
td[title] { background: #f5f1e4; }
.tabla { overflow-x: auto; }
.pestana { font-size: 12px; color: #6b675f; margin: 1.6em 0 .4em; text-transform: uppercase; letter-spacing: .06em;
  border-bottom: 1px solid #e3e0d8; padding-bottom: 4px; }
.pestana:first-child { margin-top: 0; }
.titulo-tabla { font-weight: 700; margin: 1.2em 0 .3em; }
figure.grafico { margin: 8px 0 18px; }
.notas p { margin: .3em 0; }
'''


def _vista_excel(texto):
    hojas_ = libro(texto)
    partes = []
    for nombre, hoja in zip(_nombres(hojas_), hojas_):
        partes.append(f'<p class="pestana">Hoja: {html.escape(nombre)}</p>')
        for n, tabla in enumerate(hoja['tablas']):
            if n and tabla['titulo']:
                partes.append(f'<p class="titulo-tabla">{html.escape(tabla["titulo"])}</p>')
            partes.append(_tabla_html(hoja, tabla, MAX_FILAS_VISTA) + _svg_de(hoja, tabla))
    notas = _notas(texto)
    if notas:
        partes.append(f'<p class="pestana">Hoja: {NOTAS}</p><div class="notas">' + ''.join(
            f'<p>{"<strong>" if negrita else ""}{html.escape(linea)}{"</strong>" if negrita else ""}</p>'
            for linea, negrita in notas) + '</div>')
    return ''.join(partes)


def vista(fila, contenido):
    """La vista previa en HTML de un Word o un Excel hecho por Helios, rehecha desde su markdown."""
    excel = fila['content_type'] == FORMATOS['xlsx'][0]
    cuerpo = _vista_excel(contenido) if excel else cuerpo_html(contenido, graficos=False)
    clase = 'Excel' if excel else 'Word'
    nota = ('Las celdas con fondo son fórmulas: aquí se ve su resultado; pasa el dedo o el ratón para verla.'
            if excel else 'El formato exacto se ve al abrirlo con Word o LibreOffice.')
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(fila["name"])}</title><style>{ESTILO_VISTA}</style></head><body>'
            f'<div class="aviso">Vista previa de {html.escape(fila["name"])} ({clase}). {nota}</div>'
            f'<div class="hoja">{cuerpo}</div></body></html>').encode()
