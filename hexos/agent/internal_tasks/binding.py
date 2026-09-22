"""Enlace HNF decidido por HexOS, nunca por la ficha ni por el modelo.

Primera prueba: reutilizar los pesos de text (0x0), con sesión interna fresca.
La alternancia unload/load o la residencia paralela son políticas futuras del
adaptador de runtime, no transiciones de la tarea multimedia.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelBinding:
    domain: str
    block_id: int
    load_policy: str


HANDBRAKE_TRIAL_BINDING = ModelBinding(domain='text', block_id=0x0, load_policy='reuse_resident')
