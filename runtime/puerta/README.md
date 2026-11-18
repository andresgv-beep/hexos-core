# La puerta de Helios

Usuario y contraseña delante de la interfaz, para entrar desde un navegador cualquiera sin
instalar Tailscale. Desde el 18/11.

```
navegador ──https──▶ Tailscale (Funnel, :8443) ──▶ nginx 127.0.0.1:8095 ──▶ interfaz 127.0.0.1:3000 ──▶ agente :8080
                                                     │ auth_request
                                                     ▼
                                              hexos.puerta 127.0.0.1:8096 (usuarios y sesiones)
```

- `hexos/puerta.py`: la página de entrar, las sesiones y la orden de terminal para los
  usuarios. Pruebas en `tools/puerta_test.py`.
- `nginx.conf`: nginx sin root; sin sesión, nada pasa a la interfaz. Pone `X-Helios-Usuario`
  con quien ha entrado.
- `hexos-puerta.service`, `hexos-puerta-nginx.service`: servicios de usuario.
- `instalar`: los instala y añade el origen a `HELIOS_UI_ORIGINS` de la interfaz (drop-in
  `hexos-interfaz.service.d/puerta.conf`).

La entrada de siempre por Tailscale (`https://…ts.net`, puerto 443) no cambia y no pide login.

## Instalar

```bash
runtime/puerta/instalar https://andres-system-product-name-1.tailb449cc.ts.net:8443
systemctl --user restart hexos-interfaz
tailscale serve --bg --https=8443 http://127.0.0.1:8095      # solo dentro de Tailscale
```

## Usuarios

La contraseña se escribe en la terminal y no se ve; mínimo 12 caracteres.

```bash
python3 -m hexos.puerta usuario nuevo andres
python3 -m hexos.puerta usuario clave andres      # cambiarla: cierra sus sesiones
python3 -m hexos.puerta usuario cerrar andres     # cerrar sus sesiones abiertas
python3 -m hexos.puerta usuario quitar andres
python3 -m hexos.puerta usuario lista
```

Usuarios en `~/.config/hexos/puerta/usuarios.json` (scrypt, 600); sesiones en
`~/.local/state/hexos/puerta/sesiones.json` (solo huellas). Para salir en un dispositivo:
`/_puerta/salir`.

Todos los usuarios ven el mismo Helios, el de Andrés. Dar usuario a otra persona hoy es
darle todo: conversación, notas, NAS y tarjetas. El modo invitado está por hacer.

## Abrirla a internet

```bash
tailscale funnel --bg --https=8443 http://127.0.0.1:8095
```

Si la red de Tailscale no permite Funnel, la orden da el enlace para activarlo en la consola.
Para cerrarla y volver a solo Tailscale:

```bash
tailscale funnel --https=8443 off
tailscale serve --bg --https=8443 http://127.0.0.1:8095
```

## Qué protege

- Sesión: cookie `__Host-helios` HttpOnly, Secure, SameSite=Lax; 30 días sin uso, 90 como mucho.
- 5 fallos seguidos bloquean ese usuario 15 minutos; 30 fallos en 10 minutos, a todos; nginx
  limita además los envíos del formulario a 20 por minuto.
- El formulario solo se acepta desde la propia página; `volver` solo lleva a rutas del sitio.
- Fichero de usuarios legible por otros o ilegible: no entra nadie.

Registros: `journalctl --user -u hexos-puerta` (entradas y fallos, sin contraseñas) y
`~/.local/state/hexos/puerta/logs/`.
