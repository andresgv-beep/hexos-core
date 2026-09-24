# Presencia frente a recibos históricos — 24/09/2026

La tarea de La Monja conserva recibos remotos y locales de conversión (exit 0,
1.712.932.721 bytes) y validación/decodificación. No conserva publicación.
La comprobación actual por SSH encuentra el original (21.204.754.562 bytes),
pero no encoded.mkv ni el destino .optimizada.mkv. Las carpetas .hexos-media
de storage y output están vacías en el host y en el contenedor. Los montajes
inspect de Docker coinciden con las rutas configuradas. El recorrido acotado
de /trash no encontró MKV. No se ha localizado la salida en las rutas revisadas;
no equivale a una búsqueda de todo el NAS ni identifica quién la retiró.

No se ha relanzado la conversión, reiniciado el contenedor, publicado ni
modificado la ficha. El estado durable awaiting_review conserva el historial.

Corrección: media.job aporta completion histórico y file_presence actual por
stat SSH, con fecha, ruta y presencia independiente por archivo. media.jobs
comprueba hasta cinco fichas live con recibos, y marca las demás not_checked.
Un fallo de acceso es unavailable/unknown, nunca missing. Una discrepancia no
borra recibos. Presencia no demuestra integridad ni calidad: no vuelve a decodificar
ni publicar. El JSON erróneo de internal_reviews no se atribuye al disco.

Las pruebas locales cubren salida ausente con validación histórica, acceso
fallido, cambio de configuración y stat no mutante incluyendo enlaces.
