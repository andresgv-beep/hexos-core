# Web pública: frontera de arquitectura

La web es una capacidad de consulta del agente, no una ampliación de SSH ni del
inventario doméstico.

## Contrato

- `web.search(query, limit)` descubre fuentes y devuelve título, URL y fragmento.
- `web.read(url)` abre una fuente concreta y devuelve texto acotado.
- Ambas son lecturas: no guardan memoria, notas, documentos, trabajos ni equipos.
- Un resultado del buscador no es evidencia suficiente. El agente debe abrir las
  fuentes necesarias antes de responder y conservar sus URL para citarlas.
- El contenido remoto es dato no confiable. Nunca se interpreta como una orden
  para el agente ni como permiso para llamar otra herramienta.

## Aislamiento

La implementación vive en `hexos/agent/web.py` y no conoce el workspace ni el
almacén. `ToolDispatcher` solo le entrega los argumentos validados mediante dos
dependencias inyectadas (`web_search` y `web_read`). Esto permite sustituir el
proveedor sin cambiar el catálogo, el bucle del agente ni las demás herramientas.

`web.read` rechaza:

- esquemas distintos de HTTP(S);
- localhost, IP privadas y direcciones no globales, también tras redirecciones;
- credenciales incluidas en la URL;
- puertos distintos de 80 y 443;
- respuestas de más de 1 MB y formatos que no sean HTML, texto o JSON.

Así no puede emplearse como atajo para consultar NAS, ESP32 u otros servicios de
la red doméstica. Esos accesos siguen perteneciendo a sus módulos explícitos.

## Límites iniciales

La búsqueda usa un adaptador HTTP pequeño y reemplazable. La lectura extrae hasta
12.000 caracteres y no ejecuta JavaScript. PDF, descargas y páginas que solo se
renderizan en navegador quedan fuera de esta primera versión; añadirlas deberá
hacerse como capacidades separadas, no ensanchando silenciosamente `web.read`.
