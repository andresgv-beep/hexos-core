# Lectura pasiva de la red local

`network.local` no recibe argumentos. HexOS consulta `ip -j address show`,
`ip -j route show`, `ip -j -6 route show` e `ip -j neigh show` mediante argumentos
fijos, sin shell, con timeout de cinco segundos por consulta. Requiere iproute2.
No realiza ping, escaneo de puertos, resolución DNS ni acceso al router o NAS.

Devuelve fecha UTC de lectura, direcciones propias, rutas y vecinos IPv4/IPv6
observados por el kernel. La fecha es la de lectura de la tabla, no la última
comunicación de cada vecino. REACHABLE significa alcanzable recientemente;
STALE no confirma conexión actual. FAILED, INCOMPLETE y entradas sin MAC se
cuentan como no resueltas y no se presentan como dispositivos conectados.

No garantiza descubrir todas las IP conectadas. Para un inventario más completo
haría falta otra fuente, como la tabla de clientes del router, o descubrimiento
activo. Tampoco identifica un dispositivo como NAS a partir de su IP o MAC.
Las interfaces virtuales pueden aparecer y una máquina puede tener varias IP.

La salida se limita a 32 interfaces, 64 rutas y 128 vecinos; `truncated` indica
si se ha recortado. Un fallo de consulta se comunica como error, no como red vacía.
Las respuestas de la herramienta quedan en las trazas locales habituales del chat.

Validación: pruebas de estados, comandos fijos, rechazo de argumentos y dependencia
ausente en `tools/network_test.py`. La aceptación real incluye una petición de IP
que debe ejecutar `network.local`; la calidad de su explicación se revisa manualmente.

## Corrección tras conversación real

La petición coloquial «socio busca ip en toda la red» inicialmente provocaba una
confirmación innecesaria. Después de «eso te quería decir» → «Vale», el contexto
de un solo intercambio perdía la propuesta al llegar «pues hazlo».
Ahora se conservan dos intercambios, dentro del presupuesto de caracteres existente.
La política pide ejecutar la lectura antes de anunciarla y explicar su alcance después.

La corrida privada `network-continuity-2.json` ejecutó `network.local` desde esa
primera petición coloquial y devolvió IP reales, sin confirmación. Pasan los controles
automáticos de conversación, memoria y las 50 pruebas Python. La corrida anterior
`network-continuity.json` falló y se conserva como evidencia del intento fallido.
La continuación «pues hazlo», cuando la lectura ya se ha realizado y mostrado,
todavía produce una aclaración innecesaria. No se da por resuelta toda la continuidad.
