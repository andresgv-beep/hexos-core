# Preparación del diagnóstico SSH de Synology

## Estado actual del acceso (2026-09-19)

El catálogo ya expone `nas.read`, `nas.container` y `device.connect` para equipos
registrados. El acceso se configura por el diálogo de credenciales de la interfaz
o las utilidades locales. `hosts.py` guarda credenciales y `nas_session.execute`
las usa; **ya no describe el flujo actual una sesión de ocho horas solo en RAM**.
No se ha modificado ni comprobado ningún equipo remoto en esta revisión documental.

La implementación vigente está en `hexos/agent/hosts.py`, `nas_session.py` y
`chat_backend/access.py`. El modelo no recibe una shell libre; cada operación
y sus argumentos pasan por catálogo/ejecutor. El diagnóstico de salud no autoriza
reparaciones. Los resultados de interpretación que siguen son evidencia histórica,
no certificación de que toda respuesta actual sea correcta.

## Registro histórico de integración de Synology

Los párrafos siguientes conservan la secuencia de conexión inicial, sesión
temporal y aceptación de septiembre. Las referencias a contraseña solo en RAM,
SSH rechazado o herramienta aún sin exponer describen etapas anteriores.

## Herramienta activa: nas.read

El catálogo y el ejecutor del chat incorporan `nas.read`. La sección `diagnosis`
recoge RAID, enlaces, kernel y SMART de los dispositivos encontrados. Otras secciones
son system, storage, kernel, messages y smart. Esta última recibe disk (por ejemplo sda), validado
como nombre de dispositivo; no acepta rutas o comandos. Lee identidad, atributos,
estado y registros SMART, sin iniciar tests. storage permite relacionar ata con sd
y obtener el estado RAID. El modelo debe correlacionar estas fuentes ante cortes.

El resultado de diagnosis incluye datos estructurados: correspondencia ata/sd,
miembros configurados y presentes de cada array, y atributos SMART relevantes.
No considera degradado un [1/1] [U] por ser un array de un miembro. Los valores
brutos específicos de Seagate para lectura/búsqueda se omiten del resumen para no
confundirlos con sectores dañados. Se conservan sus valores normalizados y umbrales.
La primera respuesta incluye un extracto de 12 líneas del kernel y dos pruebas SMART
anteriores, sin ejecutar nuevas. Las secciones individuales permiten ampliar.

La autenticación se mantiene exclusivamente en memoria en un proceso local durante
ocho horas. El socket Unix está en un directorio 0700 y tiene permisos 0600. El
proceso solo permite los comandos fijos, verifica la clave del host ya registrada,
limita la duración de cada lectura y no guarda la contraseña. Usa pexpect para los
prompts SSH/sudo con eco desactivado. La cuenta remota ya tiene permisos de administrador;
esta integración no modifica el NAS ni instala claves o reglas sudo.

Para abrir una sesión desde un terminal local:
`python3 -m hexos.agent.nas_session --workspace runtime/workspace`.
La contraseña se introduce en ese terminal. La sesión caduca a las ocho horas o
al reiniciar el equipo; no es todavía una configuración persistente de credenciales.
Si no existe sesión, la herramienta devuelve un error explícito.

El primer lector `ssh_diagnostics.py` mediante clave sigue disponible como preparación,
pero la ruta del chat utiliza `nas_session.py`. Los párrafos siguientes describen
el estado anterior y la primera investigación manual.

Actualización: tras habilitar el servicio y los permisos de helios, el acceso
manual por puerto 22 y sudo de lectura funciona. Se confirmó pérdida repetida del
enlace ata1/sda; el informe privado está en
`runtime/workspace/synology_diagnostico_20260912.md`. La autenticación no interactiva
y la exposición de la herramienta al chat siguen pendientes. No se guardó contraseña.

Se comprobó 192.168.1.243:22 el 2026-09-12: conexión rechazada. No se inició sesión
ni se leyeron registros del NAS. Faltan confirmar servicio/puerto, usuario y acceso.

`hexos/agent/ssh_diagnostics.py` prepara un lector de cuatro secciones fijas:
sistema y versión DSM, estado RAID/particiones, buffer del kernel y últimos
200 registros de `/var/log/messages`. No inicia tests SMART, reparaciones,
reinicios ni cambios. Los permisos efectivos del usuario pueden impedir lecturas.
Estas consultas no bastan necesariamente para determinar la causa de un corte.

El lector requiere un archivo privado `runtime/workspace/synology_ssh.json` con
`host`, `user`, `port`, `identity_file` y `known_hosts_file`. No guarda contraseñas.
Las rutas corresponden a una clave local y una clave de host previamente verificada.
Usa autenticación no interactiva, comprobación estricta del host, comandos fijos,
timeout de 15 segundos y salida limitada. No se ha creado esa configuración.

Pendiente: habilitar/verificar SSH, establecer el acceso con el usuario, comprobar
qué registros puede leer, y entonces registrar el lector en el catálogo de Helios
y probarlo con el modelo. Todavía no está expuesto como herramienta del chat.
El chat existente permanece funcionando con sus herramientas previas.

56 pruebas Python pasan, incluidas dos del lector con SSH simulado. No son una
prueba de acceso real ni un diagnóstico del disco.

Documentación de Synology:
https://kb.synology.com/en-us/DSM/tutorial/How_to_login_to_DSM_with_root_permission_via_SSH_Telnet

## Aceptación y límite de interpretación

60 pruebas Python pasan. La corrida privada nas-integration-8.json completó
la consulta real con Gemma y recogió storage/kernel/SMART de sda correctamente.
El control automático certifica esas lecturas, NO su interpretación. El modelo
aún llamó degradado a md6 pese a [1/1] [U] y al campo all_configured_members_present=true.
La herramienta está disponible para evaluación; no se considera fiable toda la
interpretación del RAID. No hay herramientas de reparación habilitadas.

Durante la integración se corrigió el adaptador nativo para admitir texto previo
a una llamada realmente delimitada. Se sigue validando el bloque completo y sus
argumentos; no se ejecutan pseudollamadas ni texto del preámbulo.

### Corrección de selección y presentación (12 septiembre)

El diagnóstico presenta primero errores de enlace respaldados por líneas del kernel
(con correspondencia a disco si existe). Una mera línea SATA link up no se etiqueta
como error. SMART tiene autoevaluación explícita PASSED/FAILED/unknown; la lectura
NVMe vacía no se presenta como salud. El recuento RAID incluye observación por array,
con gravedad y número de discos físicos fallados no determinados. Se elimina del
resumen la duplicación de /proc/mdstat; la salida completa sigue en section=storage.
Storage señala su alcance parcial y las comprobaciones ausentes. SMART sin disk
se resuelve como diagnosis mediante los discos descubiertos, sin preguntar al usuario.
La política compartida pide diagnosis para revisiones/advertencias y evita consultas
redundantes. No se modifica el broker ni sus comandos o permisos.

Validación: pruebas unitarias de ausencia de errores en enlaces normales, NVMe
unknown, recuentos RAID, alcance parcial y resolución SMART sin disco. Repeticiones
con Gemma sobre resultado guardado, sin nuevas conexiones al NAS. La primera versión
mejoró enlace/NVMe pero todavía agrupaba mal RAID: no equivale a fiabilidad garantizada
ni a una certificación diagnóstica. Qwythos requiere una nueva comparación real.

### Jerarquía de hallazgos: el disco antes que el array (12 septiembre)

El diagnóstico anterior presentaba cinco arrays con siete campos cada uno y una
sola conclusión de enlace marcada como `undetermined`. El modelo repetía lo que
más ocupaba la salida: el recuento `[12/1]` de md0/md1. Ese recuento es el valor
fijo de DSM, no once discos perdidos, y nunca fue la avería.

Ahora `diagnosis` abre con `headline` y `primary_suspect`. La selección del disco
se basa en evidencia física: eventos `device unplugged`, `PHYRdyChg`/`DevExch`,
`COMRESET failed`, reinicios del enlace, y sobre todo la velocidad renegociada.
Un `SATA link up 1.5 Gbps (SControl 310)` significa que el kernel ha limitado ese
enlace tras fallos repetidos; se contrasta con lo que el propio disco declara en
`SATA Version is: ... (current: ...)` y con la velocidad de los demás enlaces.
El modo de transferencia (`configured for UDMA/33`) confirma la degradación.

El recuento de eventos recorre el buffer completo del kernel antes del recorte a
65 líneas, de modo que una tormenta antigua no desaparece por la cola, y pesa en
el orden de sospechosos: trece eventos en un enlace superan a uno en otro.
El extracto de kernel conserva las líneas con señal en lugar de las últimas doce.

`UDMA_CRC_Error_Count` se separa de los contadores de superficie: cuenta errores
en las líneas de datos. A cero, junto a eventos del PHY, deja el contacto o la
alimentación como hipótesis más viva que el cable de datos. No demuestra la causa.

md0 y md1 se marcan `role=DSM_system_partition` con `slot_count_is_DSM_default`,
y `facts.raid_summary` resume los pools de datos en una línea. Los arrays siguen
completos en `facts.raid` con sus miembros reales; dejan de encabezar la salida.

Validación: 11 pruebas del módulo y 68 en la batería sin conexiones nuevas al NAS.
Repetición sobre la captura real `nas-integration-8.json`: identifica sda/ata1,
ST4000VN008-2DR166 serie ZGY95407, limitado a 1.5 Gbps y UDMA/33, con los cuatro
contadores de superficie a cero. Esto ordena la evidencia; no demuestra la causa
física ni certifica la interpretación del modelo, que requiere su propia prueba.

### Coste en contexto del resumen (12 septiembre)

La jerarquía nueva creció hasta 11918 caracteres frente a los 8910 anteriores, un
34% más sobre una ventana de 8192, y el chat empezó a devolver `context_full`.
El hallazgo no era el problema: lo eran las repeticiones. El aviso de que PASSED
no descarta fallos iba en cada disco; las cabeceras `ID# ATTRIBUTE_NAME` y
`Num Test_Description` quedaban sin filas debajo porque los atributos ya están en
`facts.smart_attributes`; las líneas del kernel aparecían en `diagnostic_findings`,
en `kernel.output` y resumidas en los recuentos; y cada array repetía en prosa lo
que `facts.raid_summary` dice una vez.

`diagnostic_findings` desaparece: su evidencia vive dentro de `primary_suspect`,
recortada a tres líneas, junto a `cause`. Los arrays conservan solo sus cifras,
`members`, `role` y `slot_count_is_DSM_default`. El resultado son 8196 caracteres,
714 por debajo del original, con todo el diagnóstico nuevo dentro.

Esto reduce la parte del contexto que ocupa la herramienta; no elimina por sí solo
`context_full`, que depende también del largo de la conversación sobre 8192.

`present_result` es ahora idempotente: presentar dos veces el mismo resultado daba
`KeyError: 'output'` desde que el resumen retira `/proc/mdstat`, y eso rompía el
replay sobre lo guardado. Reutiliza los hechos previos cuando la lectura cruda ya
no está. Sin correspondencia ata/sd el titular nombra el enlace, no un disco.

Validación: 12 pruebas del módulo, 69 en la batería. Corrida real con Gemma tras
reiniciar el chat: nombró sda/ata1, la limitación a 1.5 Gbps y UDMA/33, la lectura
de conexión o alimentación intermitente, y devolvió la serie ZGY95407 al pedirla.
