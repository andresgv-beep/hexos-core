# Una versión de Helios en servicio

## Referencia única

- Desarrollo: `/home/andres/Documentos/GitHub/hexos-core`, rama `main`.
- Servicio: `/home/andres/Documentos/GitHub/hexos-live`, worktree desacoplado de
  los cambios de rama del desarrollo. Backend e interfaz usan el MISMO commit.
- Versión y rutas: `/home/andres/Documentos/hexos-prueba-12b/release.env`.
- Datos existentes: `/home/andres/Documentos/hexos-prueba-12b-hq42`.
- Perfil HERA existente: `/home/andres/.helios`.

La configuración multimedia versionada (RF 18, alcance de Multimedia y borrado
de originales) y su recuperación se describen en
[MEDIA_CONFIGURATION.md](MEDIA_CONFIGURATION.md). El ejemplo de Git no
sobrescribe automáticamente el `media_jobs.json` activo del workspace.

No se duplican el historial, las tareas ni el perfil para arrancar la nueva
versión. Los pesos y el binario de Héctor siguen siendo externos al repositorio.
El antiguo worktree llamado `hexos-interface-live` pasa a llamarse `hexos-live`:
ya no es otra versión reservada a la interfaz.

## Arranque habitual

En dos terminales (si ya están activos, no iniciar duplicados):

```bash
bash /home/andres/Documentos/hexos-prueba-12b/iniciar.sh
bash /home/andres/Documentos/hexos-prueba-12b/iniciar-interfaz.sh
```

Ambos delegan en `runtime/run-local-release`, que verifica el commit declarado y
que no existan cambios locales. Rechaza una versión sucia o distinta; no hace
checkout automáticamente ni selecciona otra esfera. La UI se sirve en modo
desarrollo en `127.0.0.1:3000`; el build también se prueba, pero no se ha creado
un servicio de producción ni un arranque automático tras apagar la máquina.

Comprobación básica, sin enviar mensajes al chat:

```bash
git -C /home/andres/Documentos/GitHub/hexos-live rev-parse HEAD
git -C /home/andres/Documentos/GitHub/hexos-core rev-parse main
curl -f http://127.0.0.1:8080/api/status
curl -f http://127.0.0.1:3000/ -o /dev/null
```

`model.state=unloaded` y `error=null` con el agente `idle` es normal: carga al
escribir y libera VRAM tras inactividad. No confundirlo con servidor inaccesible.

## Actualizar sin otra mezcla de ramas

1. Trabajar y probar en el repositorio de desarrollo. Incorporar solo lo aprobado
   en `main`; las ramas de tema no son configuraciones de arranque.
2. Registrar el commit de destino. Comprobar que no hay generación activa y revisar
   las tareas persistentes antes de detener los dos procesos de servicio.
3. Con el worktree de servicio limpio, hacer checkout desacoplado del commit
   probado, ejecutar `make -C hera cli` y `npm ci` dentro de `interfaz` si cambiaron
   dependencias. No copiar bases ni secretos dentro del repositorio.
4. Actualizar `HEXOS_RELEASE` en `release.env`, arrancar ambos servicios y comprobar
   estado y UI. Esto es una operación explícita, nunca al arrancar por sorpresa.

## Respaldo y vuelta atrás

Antes de esta consolidación se conserva una copia local privada de los
lanzadores, historial SQLite, tareas, configuración multimedia y perfil en
`/home/andres/Documentos/helios-backup-20260924-XVhA1x` (directorio privado).
Las ramas originales permanecen y la versión anterior de backend quedó
conservada en el commit `551675b` (incluye la continuidad de salida).

Para volver atrás, detener los servicios, elegir una versión conocida, actualizar
el worktree y `HEXOS_RELEASE`, y arrancar. **No restaurar las bases automáticamente**:
eso perdería mensajes o efectos de trabajos ocurridos después del respaldo.
Los trabajos antiguos sin `layout_version` conservan las rutas v1; las fichas
nuevas usan v2 con títulos legibles. Una vuelta a un código previo a v2 necesita
revisar antes si ya hay fichas v2, no reanudar esas fichas a ciegas.

La copia de pruebas temporal y los informes fechados no son otra instalación
que deba usarse. El estado vigente está en `IMPLEMENTATION_STATUS.md`.
