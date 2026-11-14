"""La memoria de un proyecto: un JSON dentro de su carpeta, para remontar sin perderse.

docs/PROYECTOS_CON_FICHA_PLAN.md, fase 4, «anotar». La ficha que HexOS pone delante al
reconstruir el contexto se calculaba solo con lo hecho; faltaba lo que se quería hacer. Tras
un corte de contexto a mitad de montar un proyecto, el modelo sabía qué ficheros existían
pero no cuál era el plan ni por qué paso iba.

`<carpeta>/.helios/proyecto.json` guarda cuatro cosas:

- **objetivo** y **plan** (pasos, con cuáles están hechos) y **notas**: los escribe el modelo
  con `project.plan`. No pide aprobación: es su papel de trabajo, un solo fichero, con tope.
- **hechos**: los apunta HexOS cuando la persona aprueba un cambio. El modelo no los escribe,
  así que no puede darse por hecho algo que no pasó.

Vive en la carpeta y no en la base de datos de HexOS para que el proyecto se pueda llevar a
otro equipo con su memoria. Las lecturas y escrituras del proyecto no entran en `.helios`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from . import project_files

RUTA = Path('.helios') / 'proyecto.json'
MAX_OBJETIVO = 400
MAX_PASOS = 20
MAX_PASO = 200
MAX_NOTAS = 30
MAX_NOTA = 400
MAX_HECHOS = 40
MAX_EJECUCIONES = 12
MAX_BLOQUE = 1500                    # lo que ocupa en la ficha


def _vacia():
    return dict(version=1, objetivo='', plan=[], notas=[], hechos=[], ejecuciones=[])


def _ahora():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def leer(carpeta):
    """La memoria del proyecto, o una vacía si no hay o no se entiende."""
    try:
        cruda = json.loads((Path(carpeta) / RUTA).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return _vacia()
    if not isinstance(cruda, dict):
        return _vacia()
    memoria = _vacia()
    if isinstance(cruda.get('objetivo'), str):
        memoria['objetivo'] = cruda['objetivo'][:MAX_OBJETIVO]
    for paso in cruda.get('plan') if isinstance(cruda.get('plan'), list) else ():
        if isinstance(paso, dict) and isinstance(paso.get('paso'), str) and paso['paso'].strip():
            memoria['plan'].append(dict(paso=paso['paso'][:MAX_PASO], hecho=paso.get('hecho') is True))
    for clave in ('notas', 'hechos', 'ejecuciones'):
        for apunte in cruda.get(clave) if isinstance(cruda.get(clave), list) else ():
            if isinstance(apunte, dict) and isinstance(apunte.get('texto'), str) and apunte['texto'].strip():
                memoria[clave].append(dict(ts=str(apunte.get('ts') or ''), texto=apunte['texto'][:MAX_NOTA]))
    memoria['plan'] = memoria['plan'][:MAX_PASOS]
    return memoria


def guardar(carpeta, memoria):
    destino = Path(carpeta) / RUTA
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + '.tmp')
    temporal.write_text(json.dumps(memoria, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporal, destino)


def _texto(valor, nombre, tope):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(nombre + ' es un texto')
    return ' '.join(valor.split())[:tope]


def estado(memoria):
    """Cómo va, en lo que el modelo necesita para seguir."""
    plan = [dict(n=i, step=p['paso'], done=p['hecho']) for i, p in enumerate(memoria['plan'], 1)]
    siguiente = next((p for p in plan if not p['done']), None)
    return dict(goal=memoria['objetivo'], steps=plan, done=sum(1 for p in plan if p['done']), total=len(plan),
                next=siguiente and '%d. %s' % (siguiente['n'], siguiente['step']), notes=len(memoria['notas']))


def apuntar(store, goal=None, steps=None, done=None, note=None):
    """Lo que escribe el modelo: objetivo, plan, un paso hecho o una nota. Al menos una cosa."""
    proyecto, base = project_files.proyecto_activo(store)
    if goal is None and steps is None and done is None and note is None:
        raise ValueError('Hace falta al menos uno: goal (el objetivo), steps (los pasos del plan), done (el número '
                         'del paso terminado) o note (algo que recordar).')
    memoria = leer(base)
    if goal is not None:
        memoria['objetivo'] = _texto(goal, 'goal', MAX_OBJETIVO)
    if steps is not None:
        if not isinstance(steps, list) or not steps or len(steps) > MAX_PASOS:
            raise ValueError('steps es la lista de pasos del plan, de 1 a %d' % MAX_PASOS)
        # Rehacer el plan no borra lo ya hecho: un paso con el mismo texto conserva su marca.
        hechos = {p['paso'] for p in memoria['plan'] if p['hecho']}
        nuevos = [_texto(paso, 'cada paso de steps', MAX_PASO) for paso in steps]
        memoria['plan'] = [dict(paso=paso, hecho=paso in hechos) for paso in nuevos]
    if done is not None:
        if type(done) is not int or not 1 <= done <= len(memoria['plan']):
            raise ValueError('done es el número del paso terminado, de 1 a %d. El plan tiene %d pasos.' % (
                max(len(memoria['plan']), 1), len(memoria['plan'])))
        memoria['plan'][done - 1]['hecho'] = True
    if note is not None:
        memoria['notas'] = (memoria['notas'] + [dict(ts=_ahora(), texto=_texto(note, 'note', MAX_NOTA))])[-MAX_NOTAS:]
    guardar(base, memoria)
    aviso = 'Apuntado en la memoria del proyecto. HexOS te la pondrá delante si se pierde el contexto.'
    if done is not None:
        # done marca un paso, no «hasta ese»: el 14/11 el E4B mandó done=3 queriendo decir
        # los tres, y quedaron dos sin marcar. Mejor avisar que dar por hecho lo que no consta.
        antes = [str(i) for i, p in enumerate(memoria['plan'][:done - 1], 1) if not p['hecho']]
        if antes:
            aviso += (' Se ha marcado solo el paso %d. Siguen pendientes los anteriores: %s. Si también están '
                      'terminados, marca cada uno con done.' % (done, ', '.join(antes)))
    return dict(estado(memoria), project=proyecto['name'], saved=str(RUTA), note=aviso)


def hecho(carpeta, texto):
    """Lo apunta HexOS, no el modelo: algo que ha pasado de verdad en el proyecto."""
    try:
        memoria = leer(carpeta)
        memoria['hechos'] = (memoria['hechos'] + [dict(ts=_ahora(), texto=' '.join(texto.split())[:MAX_NOTA])])[-MAX_HECHOS:]
        guardar(carpeta, memoria)
    except OSError:
        pass                                            # la memoria no puede tumbar una aprobación


def ejecutado(carpeta, orden, resultado):
    """También lo apunta HexOS: qué se ejecutó y cómo acabó. Repetir una orden sustituye su apunte."""
    try:
        memoria = leer(carpeta)
        orden = ' '.join(orden.split())[:200]
        previas = [e for e in memoria['ejecuciones'] if not e['texto'].startswith(orden + ' → ')]
        memoria['ejecuciones'] = (previas + [dict(ts=_ahora(), texto=orden + ' → ' + resultado)])[-MAX_EJECUCIONES:]
        guardar(carpeta, memoria)
    except OSError:
        pass


def bloque(carpeta):
    """La memoria tal como va en la ficha: objetivo, plan con lo hecho, y lo último apuntado."""
    memoria = leer(carpeta)
    if not (memoria['objetivo'] or memoria['plan'] or memoria['notas'] or memoria['hechos'] or memoria['ejecuciones']):
        return ('Memoria del proyecto: vacía. Cuando haya un objetivo o un encargo de varios pasos, apúntalo con '
                'project_plan (goal y steps), marca cada paso al terminarlo (done) y deja en note lo que convenga '
                'recordar: es lo que HexOS te pondrá delante si se pierde el contexto.')
    lineas = ['Memoria del proyecto (%s; la llevas tú con project_plan):' % RUTA]
    if memoria['objetivo']:
        lineas.append('Objetivo: ' + memoria['objetivo'])
    if memoria['plan']:
        lineas.append('Plan: ' + ' '.join('%d. [%s] %s' % (i, 'hecho' if p['hecho'] else 'pendiente', p['paso'])
                                          for i, p in enumerate(memoria['plan'], 1)))
        siguiente = estado(memoria)['next']
        lineas.append('Siguiente paso: ' + siguiente if siguiente else 'Todos los pasos del plan están hechos.')
    if memoria['notas']:
        lineas.append('Notas: ' + ' | '.join(n['texto'] for n in memoria['notas'][-5:]))
    if memoria['hechos']:
        lineas.append('Escrito con aprobación de la persona: ' + ' | '.join(h['texto'] for h in memoria['hechos'][-6:]))
    if memoria['ejecuciones']:
        lineas.append('Últimas ejecuciones (las apunta HexOS): ' + ' | '.join(e['texto'] for e in memoria['ejecuciones'][-5:]))
    lineas.append('Mantenla al día: done al terminar un paso, note para lo que convenga recordar.')
    texto = '\n'.join(lineas)
    return texto if len(texto) <= MAX_BLOQUE else texto[:MAX_BLOQUE - 40].rsplit(' ', 1)[0] + ' […recortada]'
