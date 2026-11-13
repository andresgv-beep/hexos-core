#!/usr/bin/python3
"""Banco del selector de grupos: ¿pide el grupo que hace falta para cada frase?

El selector decide qué herramientas ve el modelo en el turno. Su guía
(`catalog.GROUP_GUIDANCE`) se ha retocado muchas veces midiendo con frases que nadie
guardó: el 13/11 se cambió cuatro veces seguidas sin poder repetir la medida. Este banco
son esas frases, escritas y etiquetadas, para que un cambio en la guía se compare con el
anterior con los mismos casos.

Modelo real, sin Agent: llama a `tool_groups.elegir` tal como lo hace el turno. Helios
debe tener la gráfica libre.

    python3 tools/banco_selector.py --runtime <helios_runtime> --model <hnf> --template <jinja>
    python3 tools/banco_selector.py ... --guia-de 982ed04      # la guía de otro commit

Un caso acierta si el selector pide todos los grupos esperados; con [] esperado, si no
pide ninguno. Lo que pide de más se cuenta aparte: no deja al modelo sin herramientas,
pero cuesta tokens y es lo que confunde a un modelo pequeño.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))

# (ventana, frase, grupos que hacen falta)
CASOS = [
    # --- sistema: este PC
    ('agente', '¿tengo gimp instalado?', ['sistema']),
    ('agente', '¿tengo algún juego?', ['sistema']),
    ('agente', '¿qué programas tengo instalados?', ['sistema']),
    ('agente', '¿podrías encontrar la app de ChatGPT?', ['sistema']),
    ('agente', '¿por qué va lento el ordenador?', ['sistema']),
    ('agente', '¿qué consume más ahora mismo?', ['sistema']),
    ('agente', '¿cuánta memoria le queda a la gráfica?', ['sistema']),
    ('agente', '¿cuánta batería queda?', ['sistema']),
    ('agente', '¿cuánto disco libre tengo?', ['sistema']),
    ('agente', '¿está activo ssh?', ['sistema']),
    ('agente', '¿está docker instalado?', ['sistema']),
    ('agente', 'mira si hay errores en el registro del sistema', ['sistema']),
    ('agente', '¿puedo compilar un programa en C en este ordenador?', ['sistema']),
    ('agente', '¿tengo Rust instalado?', ['sistema']),
    ('agente', '¿qué lenguajes de programación puedo usar aquí?', ['sistema']),
    ('agente', 'instala el programa sl con apt', ['sistema']),
    ('agente', 'desinstala nomachine de este equipo', ['sistema']),
    # --- proyecto: la carpeta del proyecto puesto, por dentro
    ('agente', '¿qué hay dentro de la carpeta del proyecto?', ['proyecto']),
    ('agente', '¿qué ficheros tiene el proyecto?', ['proyecto']),
    ('agente', 'explícame qué hace el fichero src/main.cu', ['proyecto']),
    ('agente', 'busca dónde se usa lanzar_atencion en el código', ['proyecto']),
    ('agente', 'revisa el README del proyecto y dime si le falta algo', ['proyecto']),
    ('agente', '¿ves algún fallo en kernels/atencion.cu?', ['proyecto']),
    # --- archivos: lo que está en el NAS
    ('agente', 'busca la película Interstellar en el NAS', ['archivos']),
    ('agente', '¿qué hay en la carpeta Compartido del synology?', ['archivos']),
    ('agente', 'lee el archivo notas-raid.txt del NAS', ['archivos']),
    ('agente', '¿cuántas películas hay en las carpetas marvel del synology 1?', ['archivos']),
    # --- equipos: otros ordenadores y la red
    ('agente', '¿qué equipos tengo en casa?', ['equipos']),
    ('agente', 'conéctate al synology', ['equipos']),
    ('agente', '¿cuánto espacio libre tiene el NAS?', ['equipos']),
    ('agente', '¿qué contenedores corren en el NAS?', ['equipos']),
    ('agente', 'mira qué dispositivos hay en la red', ['equipos']),
    # --- multimedia
    ('agente', 'comprime la película Avatar', ['multimedia']),
    ('agente', '¿cómo va la compresión de vídeo?', ['multimedia']),
    ('agente', 'pausa la cola de vídeo', ['multimedia']),
    # --- basta con conversar
    ('agente', 'hola, ¿qué tal?', []),
    ('agente', 'gracias', []),
    ('agente', 'jajaja vale', []),
    ('agente', 'explícame en dos frases qué es la cuantización de un modelo', []),
    ('agente', '¿qué opinas de medir antes de optimizar?', []),
    # --- ventana Chat
    ('chat', 'apunta que el martes hay cena', ['notas']),
    ('chat', 'enséñame mis notas', ['notas']),
    ('chat', 'borra la nota de la cena', ['notas']),
    ('chat', '¿qué informes tengo guardados?', ['informes']),
    ('chat', 'hola', []),
]


def guia_de(ref):
    """La guía de grupos tal como estaba en otro commit, para comparar redacciones."""
    fuente = subprocess.check_output(['git', '-C', str(CORE), 'show', ref + ':hexos/agent/catalog.py'], text=True)
    espacio = {'__name__': 'catalogo_antiguo'}
    exec(compile(fuente, ref + ':catalog.py', 'exec'), espacio)
    return espacio['GROUP_GUIDANCE']


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--template', required=True)
    parser.add_argument('--ctx', type=int, default=16384)
    parser.add_argument('--guia-de', help='Commit del que tomar la guía de grupos, en vez de la actual')
    parser.add_argument('--salida', type=Path, help='Dónde dejar el detalle en JSON')
    args = parser.parse_args()
    from hexos.agent import catalog, tool_groups
    from hexos.agent.native import NativeRuntime
    if args.guia_de:
        catalog.GROUP_GUIDANCE = guia_de(args.guia_de)
    filas = []
    with tempfile.TemporaryDirectory(prefix='hexos-banco-selector-') as tmp:
        runtime = NativeRuntime(args.runtime, args.model, args.ctx, tmp, args.template)
        try:
            for ventana, frase, esperado in CASOS:
                # Lo mismo que `tool_groups.elegir`, guardando la salida cruda: cuando no vale
                # hace falta ver qué contestó, no solo que se descartó.
                runtime.send(tool_groups._prompt(runtime, '', frase, ventana), auxiliar=True)
                cabecera, crudo = runtime.event()
                elegido = tool_groups.interpretar(crudo, ventana) if cabecera[4] == 'eos' else None
                if elegido is None:
                    acierta, sobra = False, []           # «no sé»: se ofrecería todo
                elif not esperado:
                    acierta, sobra = elegido == [], elegido
                else:
                    acierta = all(g in elegido for g in esperado)
                    sobra = [g for g in elegido if g not in esperado]
                filas.append(dict(ventana=ventana, frase=frase, esperado=esperado, elegido=elegido,
                                  acierta=acierta, sobra=sobra, crudo=crudo, fin=cabecera[4]))
                if not acierta or sobra:
                    print(('FALLA ' if not acierta else 'sobra ') + json.dumps(
                        dict(frase=frase, esperado=esperado, elegido=elegido,
                             **({} if elegido is not None else dict(crudo=crudo[:160], fin=cabecera[4]))),
                        ensure_ascii=False), flush=True)
        finally:
            runtime.close()
    resumen = dict(guia=args.guia_de or 'actual', casos=len(filas), aciertos=sum(f['acierta'] for f in filas),
                   con_grupos_de_mas=sum(bool(f['sobra']) for f in filas),
                   sin_respuesta=sum(f['elegido'] is None for f in filas))
    if args.salida:
        args.salida.write_text(json.dumps(dict(resumen=resumen, casos=filas), ensure_ascii=False, indent=1))
    print('RESUMEN', json.dumps(resumen, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
