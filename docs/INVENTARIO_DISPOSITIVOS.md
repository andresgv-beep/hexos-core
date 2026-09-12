# Inventario local de dispositivos

El inventario se guarda en `network_devices`, dentro del SQLite del espacio de
trabajo. Sobrevive al reinicio y a limpiar el contexto del chat.

- `device.refresh`: obtiene una nueva lectura pasiva y guarda observaciones.
- `device.list`: recupera el inventario; acepta búsqueda por nombre, tipo, IP o MAC.
- `device.identify`: guarda el nombre y tipo atribuidos por el usuario, junto con
  el mensaje original y su id. HexOS recibe el turno actual directamente del
  ejecutor; el modelo no tiene que reconstruir citas ni aportar ids de mensajes.

Se agrupa por MAC e interfaz. Cada registro conserva hasta 32 direcciones históricas,
las direcciones de la última observación y su estado. Las identidades no se copian
entre MAC distintas cuando una IP cambia de dueño. Las MAC aleatorias o duplicadas
pueden impedir reconocer correctamente un equipo físico: esta clave no es autenticación.
Ausencia en una lectura pasiva no significa desconexión.

Una identificación exige que el mensaje del usuario incluya la dirección o un
sufijo IPv4 inequívoco y el nombre atribuido en el mismo segmento separado por
comas. No se aceptan nombres inventados fuera del mensaje. Una cita anterior no
reemplaza una identificación más reciente. Los sufijos ambiguos se rechazan.
La relación semántica entre las palabras de la cita sigue dependiendo del modelo;
la validación de texto no demuestra por sí sola que haya interpretado bien una negación.

El modelo tiene instrucciones de consultar el inventario antes de pedir la IP de
un equipo identificado. El inventario no da acceso al NAS, no proporciona credenciales
ni autoriza actuaciones. La herramienta de red sigue siendo pasiva. Para conocer
el estado actual debe hacer una nueva consulta, no tratar el inventario como telemetría.

Ejemplos: «Guarda los dispositivos de la red en el inventario», «Recuerda:
192.168.1.10 es mi NAS Faro», «Consulta el inventario y dime qué IP tiene mi NAS Faro».
La IP del ejemplo es ilustrativa; debe usarse la dirección real del equipo.

Las pruebas de persistencia, reasignación de IP, citas inválidas y correcciones
están en `tools/devices_test.py`. El recorrido de aceptación con Gemma usa un
dispositivo simulado y una base temporal; no asigna nombres de prueba a equipos reales.

## Resultado de aceptación (2026-09-12)

52 pruebas Python pasan. En `runtime/logs/conversation-focus-fix/device-inventory-2.json`,
Gemma guardó el inventario, identificó Faro como NAS, corrigió el nombre a Puerto
y recuperó su IP mediante `device.list` tras limpiar contexto. Se comprobó además
la identidad persistida en SQLite. La primera corrida falló porque el modelo
inventaba un `source_id`; ese argumento se eliminó y HexOS resuelve la fuente.

La suite amplia no pasa íntegra: sigue fallando el replay antiguo `replay_56`
sobre el nombre del usuario. El éxito del inventario no certifica toda la conversación.
Se sembró el inventario real con 23 registros observados pasivamente, sin nombres
inventados ni acceso al contenido de dispositivos.

Seguimiento: la captura con «el que termina en 243 como synology, el 131 como nimos
nas» destapó que el modelo reconstruía mal la cita e incluso cambiaba .243 por
.249. Se eliminó `evidence` del esquema y se resolvieron los sufijos en HexOS.
La regresión añade .249 como distractor y comprueba también que no se intercambien
los nombres. Las dos asociaciones reales se guardaron desde el mensaje original:
192.168.1.243 → synology; 192.168.1.131 → nimos nas.

La corrida `suffix-identification.json` completó esa petición literal con dos
llamadas reales a `device.identify`, usando los sufijos 243 y 131. La comprobación
de SQLite confirmó ambos nombres y que .249 quedaba sin identificar. También
pasó guardar → identificar → corregir → recuperar. Pasan 54 pruebas Python;
la suite amplia mantiene únicamente el fallo conocido `replay_56`.

## Consultar identidades durante una lectura de red

Otra captura mostró una búsqueda literal de `synology OR nimos nas` sin resultados,
seguida de intentos de `device.identify` al pedir simplemente mostrar los nombres.
`device.list` admite ahora OR, prioriza identificados y devuelve registros compactos
sin repetir toda la evidencia. Un filtro vacío de resultados no prueba inventario vacío.

`network.local` une las observaciones con el inventario por MAC e interfaz y devuelve
`identity` en cada vecino e `identified_neighbors` al principio del resultado. Esta
unión es de solo lectura: no cambia identidades ni las copia a otra MAC que use la
misma IP. Las instrucciones distinguen consultar identidades de escribirlas.

En `inventory-read-join.json`, Gemma respondió a la consulta de guardados mediante
`device.list`, con ambos nombres e IP correctos. Ante «vuelve a buscar ips y
identificalas» ejecutó solo `network.local` y mostró synology (.243), nimos nas
(.131) y el dispositivo sin nombre (.249), indicando STALE. No pidió confirmación
ni llamó a `device.identify`. Las 54 pruebas Python pasan, con comprobación de
unión sin escrituras y sin transferir identidad a otra MAC. La suite amplia falla
en los replays antiguos de nombre `replay_54` y `replay_56`; no se declara estable
toda la conversación por el éxito de este recorrido.
