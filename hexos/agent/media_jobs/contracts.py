"""Bordes de E/S: una operación debe reconciliar su clave antes de repetir efectos."""
from typing import Protocol


class FileFailure(Exception):
    """Fallo comprobado propio de esta película; no impide pasar a la siguiente."""


class SharedFailure(Exception):
    """Disco/servicio/exclusividad: requiere pausar el lote."""


class UncertainEffect(Exception):
    """No se conoce el efecto. Reconciliar con la MISMA clave, nunca relanzar a ciegas."""


class Files(Protocol):
    def stop(self, job: dict, key: str) -> dict:
        """Cancelar workers de archivos propios y confirmar que dejaron de escribir."""
        ...

    def stage(self, job: dict, key: str) -> dict:
        """Revalidar origen/espacio, copiar completo fuera de watch; conservar original."""
        ...

    def verify(self, job: dict, key: str) -> dict:
        """Comprobar identidad, duración, pistas, códec y salida final; devolver valid."""
        ...

    def publish(self, job: dict, key: str) -> dict:
        """Publicar en destino sin sobrescribir. Reconciliar publicación ya hecha."""
        ...

    def index(self, job: dict, key: str) -> dict:
        """Refrescar catálogo tras publicación; devolver indexed."""
        ...


class HandBrake(Protocol):
    def start(self, job: dict, key: str) -> dict:
        """Inicio durable; misma clave devuelve el mismo run_id, incluso tras reinicio."""
        ...

    def observe(self, job: dict) -> dict:
        """status, run_id, percent, phase, eta_seconds, output_bytes, activity_counter."""
        ...

    def stop(self, job: dict, key: str) -> dict:
        """Detener solo run_id propio. stopped=True solo tras comprobarlo."""
        ...

    def restart(self, job: dict, key: str) -> dict:
        """Solo con exclusividad comprobada; confirmar contenedor sano y ejecución ausente."""
        ...

# Todas las llamadas deben volver antes de que expire el lease del worker.
# Una copia/verificación/publicación larga se ejecuta remotamente y devuelve
# pending=True con progreso. El siguiente tick reconcilia la misma clave. Nunca
# bloquear un tick durante una copia de decenas de GB ni asumir que expirar el
# lease autoriza un segundo proceso remoto.
