"""Fichas de técnica: oficio que el modelo puede no dominar, puesto delante cuando toca.

Pedido por Andrés el 15/11. El 26B razona bien y aun así montó tres veces una calculadora con
los botones aplastados abajo, y añadió una columna a una tabla sin pensar en la base que ya
existía. No es falta de cabeza: son técnicas que se saben o no. La idea no es darle el programa
hecho, sino enseñarle la técnica para que la aplique él en lo que toque.

Una ficha es un fichero de texto corto: cuándo se usa, la regla, por qué, y un ejemplo mínimo.

    # Título
    aplica: tkinter, interfaz
    (línea en blanco)
    cuerpo…

Las de serie van en `hexos/agent/tecnicas_fichas/`. Las de la persona, en `~/Helios/tecnicas/`
(o `HEXOS_TECNICAS_HOME`): una con el mismo nombre de fichero sustituye a la de serie, y un
fichero vacío la apaga.

HexOS elige las que tocan mirando qué usa el proyecto (lo que importan sus ficheros, sus
extensiones, el objetivo y el plan apuntados) y qué se pide en el turno. No dependen de que
el modelo se acuerde de pedirlas ni gastan una herramienta. Cada ficha se da una vez por
contexto: si el contexto se reconstruye, vuelven.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import project_files

DE_SERIE = Path(__file__).with_name('tecnicas_fichas')
MAX_FICHA = 1800                     # caracteres del cuerpo; lo que pase se corta
MAX_POR_VEZ = 4                      # fichas que se dan de una vez
MAX_MIRADOS = 80                     # ficheros del proyecto en los que se buscan señales
MAX_LEIDO = 6000                     # bytes del principio de cada uno
IMPORTA = re.compile(r'^\s*(?:from|import)\s+([A-Za-z_][\w.]*)', re.M)
INCLUYE = re.compile(r'#\s*include\s*[<"]([\w./]+)[>"]')
PALABRA = re.compile(r'[a-záéíóúñ0-9_+#.]{2,}', re.I)


def casa():
    return Path(os.environ.get('HEXOS_TECNICAS_HOME') or Path.home() / 'Helios' / 'tecnicas')


def _leer(ruta):
    """Una ficha desde su fichero, o None si no tiene forma de ficha."""
    try:
        texto = ruta.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None
    lineas = texto.strip().split('\n')
    if len(lineas) < 3 or not lineas[0].startswith('#'):
        return None
    cabecera = next((l for l in lineas[1:4] if l.casefold().startswith('aplica:')), None)
    if not cabecera:
        return None
    aplica = {p.strip().casefold() for p in cabecera.split(':', 1)[1].split(',') if p.strip()}
    cuerpo = '\n'.join(lineas[lineas.index(cabecera) + 1:]).strip()
    if not aplica or not cuerpo:
        return None
    if len(cuerpo) > MAX_FICHA:
        cuerpo = cuerpo[:MAX_FICHA].rsplit('\n', 1)[0] + '\n[…ficha recortada]'
    return dict(nombre=ruta.stem, titulo=lineas[0].lstrip('# ').strip(), aplica=aplica, cuerpo=cuerpo)


def cargar():
    """Todas las fichas vigentes, por nombre. Las de la persona mandan sobre las de serie."""
    fichas = {}
    for carpeta in (DE_SERIE, casa()):
        if not carpeta.is_dir():
            continue
        for ruta in sorted(carpeta.glob('*.md')):
            ficha = _leer(ruta)
            if ficha:
                fichas[ruta.stem] = ficha
            elif carpeta != DE_SERIE:
                fichas.pop(ruta.stem, None)             # vacía o sin forma: apaga la de serie
    return [fichas[nombre] for nombre in sorted(fichas)]


def _palabras(texto):
    return {p.casefold().strip('.') for p in PALABRA.findall(texto or '')}


def senales(carpeta, *textos):
    """De qué va el proyecto, en palabras sueltas: lo que importa, sus extensiones y lo dicho."""
    vistas = set()
    for texto in textos:
        vistas |= _palabras(texto)
    try:
        base = Path(carpeta).resolve()
        mirados = 0
        for completa, relativa in project_files._recorrer(base, base):
            if mirados >= MAX_MIRADOS:
                break
            mirados += 1
            if relativa.suffix:
                vistas.add(relativa.suffix.casefold())
            if relativa.suffix.casefold() not in ('.py', '.c', '.h', '.cc', '.cpp', '.hpp', '.cu', '.js', '.ts'):
                continue
            try:
                with open(completa, 'rb') as fichero:
                    principio = fichero.read(MAX_LEIDO).decode('utf-8', errors='replace')
            except OSError:
                continue
            for modulo in IMPORTA.findall(principio):
                vistas |= {modulo.casefold(), modulo.split('.')[0].casefold()}
            for cabecera in INCLUYE.findall(principio):
                vistas.add(Path(cabecera).stem.casefold())
    except OSError:
        pass
    return vistas


def elegir(vistas, ya=()):
    """Las fichas que casan con esas señales y aún no se han dado, las más concretas primero."""
    candidatas = []
    for ficha in cargar():
        comunes = ficha['aplica'] & vistas
        if comunes and ficha['nombre'] not in ya:
            # Más concreta la que casa con más de sus propias palabras; a igualdad, por nombre.
            candidatas.append((-len(comunes) / len(ficha['aplica']), ficha['nombre'], ficha))
    return [ficha for _, _, ficha in sorted(candidatas)[:MAX_POR_VEZ]]


def bloque(fichas):
    """Las fichas tal como van delante del turno."""
    if not fichas:
        return ''
    partes = ['\nTÉCNICAS (fichas de oficio que HexOS te da para este trabajo; aplícalas en lo que escribas, '
              'no las recites):']
    for ficha in fichas:
        partes.append('## ' + ficha['titulo'] + '\n' + ficha['cuerpo'])
    return '\n\n'.join(partes) + '\n'
