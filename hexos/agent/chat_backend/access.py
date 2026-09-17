"""Credenciales: circuito de interfaz separado de la conversación."""
from __future__ import annotations

from uuid import uuid4
from .. import hosts
from ..work import now, string
from .state import Environment, SessionState


class CredentialService:
    def __init__(self, env: Environment, session: SessionState, stores):
        self.env = env
        self.session = session
        self.stores = stores

    def dismiss_access(self, device):
        """Retirar una petición de acceso sin guardar nada.

        «Ahora no» tenía que valer también en el servidor: mientras la petición
        siguiera puesta, la interfaz la volvía a abrir en cuanto se recargara, y
        la persona se quedaba con la ventana delante sin poder escribir.
        """
        device = string(device, 'device', 64)
        if (self.session.credential_request or {}).get('device') != device.casefold():
            raise ValueError('No hay ninguna petición de acceso pendiente para ' + repr(device))
        self.session.credential_request = None
        return dict(dismissed=device.casefold(), saved=False,
                    note='Petición retirada. No se ha guardado ninguna credencial y el equipo '
                         'sigue sin acceso; se volverá a pedir cuando se intente leerlo.')

    def save_access(self, payload):
        """Guarda una credencial pedida por Helios. No pasa por la conversación ni por el modelo."""
        if payload.get('dismiss') is True:
            if set(payload) - {'device', 'dismiss'}:
                raise ValueError('Para retirar la petición basta con device y dismiss')
            return self.dismiss_access(payload.get('device'))
        if set(payload) - {'device', 'user', 'password', 'port', 'host'}:
            raise ValueError('Campos permitidos: device, user, password, port, host')
        device = string(payload.get('device'), 'device', 64)
        user = string(payload.get('user'), 'user', 64)
        password = payload.get('password')
        if not isinstance(password, str) or not password:
            raise ValueError('Falta la contraseña')
        port = payload.get('port', 22)
        # Sin dirección escrita, sale del inventario y nunca del cliente: así la ventana
        # no puede decir un equipo y mandar el acceso a otro. Con dirección escrita manda
        # esa —es la única forma de llegar a un equipo que no está en esta red—, se valida
        # antes de tocar nada y queda anotada en el turno para que se vea a dónde fue.
        fijada = hosts.address(payload['host']) if payload.get('host') else None
        located = dict(host=fijada, pinned=True) if fijada else hosts.resolve(self.env.workspace, device)
        hosts.save(self.env.workspace, device, user, password, port, fijada)
        retomar = None
        if (self.session.credential_request or {}).get('device') == device.casefold():
            retomar = self.session.credential_request.get('pending_request')
            self.session.credential_request = None
        # Sin esta anotación el modelo sigue leyendo en su contexto que le falta el
        # acceso y responde que no lo tiene en lugar de volver a intentar la lectura.
        note = ('[El operador acaba de guardar el acceso a ' + device.casefold() + ' (' + located['host'] +
                (', dirección fija' if located.get('pinned') else '') +
                ') desde la ventana de la interfaz. Ya está disponible: si te piden algo de ese equipo, '
                'vuelve a llamar a la herramienta en lugar de decir que faltan credenciales. '
                'La contraseña no está aquí ni la vas a ver.]')
        with self.stores() as store:
            store.db.execute('INSERT INTO conversation VALUES (?,?,?,?,?)',
                             (uuid4().hex, now(), 'user', note, note))
            store.db.commit()
        return dict(saved=True, device=device.casefold(), user=user,
                    host=located['host'], mac=located.get('mac'), pinned=bool(fijada),
                    resume=retomar,
                    note='Guardado en credentials.json con permisos 600. '
                         'No se ha escrito en la conversación ni se ha mostrado al modelo. '
                         'resume es lo que se estaba pidiendo cuando faltó el acceso: la interfaz '
                         'lo reenvía para no hacer repetir la petición.')
