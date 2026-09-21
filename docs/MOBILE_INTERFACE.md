# Vista móvil: primera integración

MobileWorkspace es presentación del estado de HeliosExperience: no crea transport,
sesión, almacén ni agente. Paneles con scroll-snap horizontal: notas, chat, código
y visualización. La escritura y los adjuntos siguen usando el compositor común.
El historial y las respuestas usan los componentes existentes. El iframe conserva
su sandbox y CSP; una visualización no obtiene acceso a la red del servidor.

## Acceso desde otros dispositivos

Las peticiones del navegador usan rutas relativas `/api/helios`: localhost en el
móvil no apunta al ordenador servidor. Servir UI y API bajo el mismo origen.
El proxy actual solo autoriza los orígenes locales de desarrollo; no ampliar a
`*` ni reescribir cualquier Origin para conseguir que funcione remotamente.

Antes de habilitar LAN o acceso exterior: elegir dirección/origen de despliegue,
autenticación y HTTPS o una VPN privada. Mantener el backend en loopback y publicar
solo una entrada autenticada; incluir adjuntos y lecturas, no solo escrituras.
No exponer Vite ni abrir puertos del router como despliegue de producción.
HTTPS es también necesario para el futuro micrófono en navegadores remotos.

## Pendiente antes de considerarlo multidispositivo completo

- Recuperar el turno en curso iniciado desde otro cliente y actualizar historial
  sin duplicar mensajes; hoy el seguimiento progresivo pertenece al emisor local.
- Sincronizar artefactos abiertos y seleccionados entre dispositivos.
- Validar teclado y áreas seguras en Safari iOS y Chrome Android reales.
- Afinar paneles, desplazamiento vertical y navegación con teclado/lector.

Esta entrega no habilita acceso público ni afirma sincronización en vivo completa.

## Prueba temporal en LAN de confianza

Con autorización del operador se puede arrancar desarrollo ligado a su IP LAN:
`HELIOS_UI_HOST=IP-LAN HELIOS_UI_ORIGINS=http://IP-LAN:3000 npm run dev -- --port 3000`.
La variable autoriza orígenes exactos separados por comas, sin comodines. No es
autenticación: todos los dispositivos de esa red pueden acceder. Usar solo en
una red de confianza y no reenviar ese puerto a Internet. El backend sigue en
127.0.0.1:8080. La dirección depende del DHCP; esta configuración es temporal.
