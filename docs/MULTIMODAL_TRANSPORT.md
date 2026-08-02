# Transporte multimodal HexOS → Héctor

## Responsabilidades

La UI decodifica el fichero seleccionado y entrega píxeles RGB8. HexOS valida
la geometría y transporta el buffer; Héctor selecciona el adaptador declarado
por el HNF, ejecuta la torre y conserva la conversación en su KV.

Ninguna capa decide por nombre de modelo:

- `/api/status` dice si `vision.status` es `runtime_ready`;
- la UI muestra adjuntos únicamente en ese caso;
- HexOS usa un adjunto genérico de tipo `ENGINE_ATTACHMENT_RGB8`;
- `helios_chat` resuelve el adaptador por su identificador de metadatos.

## Endpoint RGB8 v1

```text
POST /api/attachment/rgb8
Content-Type: application/octet-stream
X-Image-Width: <píxeles>
X-Image-Height: <píxeles>
X-Image-Stride: <bytes por fila>
Content-Length: <stride * height>

<RGBRGBRGB...>
```

Una respuesta `202` deja la imagen pendiente. El siguiente `POST /api/chat`
la consume junto a su texto. Solo puede existir un adjunto pendiente en el
contrato visual v1.

El cuerpo debe medir exactamente `stride * height`, el stride debe contener al
menos `width * 3` bytes y el límite absoluto es 300 MiB. El servidor recibe el
cuerpo como binario, no usa `strlen`, no lo convierte a base64 y no lo escribe
en disco.

Mientras transfiere el frame, el motor entra en estado `staging`. Chat y otro
adjunto reciben `409` hasta que Héctor confirma el nuevo prompt `tú>`. Esto
evita que dos hilos HTTP intercalen texto dentro del payload binario.

## Framing local

HexOS traduce el request a la tubería privada de Héctor:

```text
/adjunto-rgb8 WIDTH HEIGHT STRIDE BYTES\n
<BYTES bytes>\n
```

La escritura de cabecera, payload y separador está protegida por un único
mutex. Una longitud corrupta no intenta recuperar el flujo silenciosamente.

## Pruebas

`make -C hexos attachment-bridge-test` usa un motor falso estricto que verifica
cada byte, el estado `staging`, el evento de confirmación y el turno posterior.
También se verificó manualmente el endpoint HTTP completo con ese motor.

La certificación real de Héctor usa el HNF combinado Gemma 4: imagen, respuesta
visual y seguimiento textual en el mismo KV. La prueba HTTP real se repetirá
cuando la GPU esté libre; durante este corte un juego ocupaba 7005 MiB y el
modelo no podía cargarse, por lo que no se mató ningún proceso ajeno.
