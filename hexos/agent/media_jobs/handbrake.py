"""Capacidad de producción desactivada hasta validar el transporte real.

El protocolo está en contracts.HandBrake. Ningún método del placeholder ejecuta
shell, copia ficheros o reinicia contenedores. El runner recibe un adaptador
inyectado; nunca degrada silenciosamente una tarea live a simulación.
"""
from .contracts import SharedFailure


class UnconfiguredHandBrake:
    mode = 'live'

    def start(self, job, key):
        raise SharedFailure('Adaptador NAS/HandBrake todavía no configurado ni validado')

    def observe(self, job):
        raise SharedFailure('Observación NAS/HandBrake no configurada')

    def stop(self, job, key):
        raise SharedFailure('Parada NAS/HandBrake no configurada')

    def restart(self, job, key):
        raise SharedFailure('Reinicio NAS/HandBrake no configurado')
