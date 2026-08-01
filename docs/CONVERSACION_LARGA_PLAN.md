# Conversación larga sin desvarío — plan

> Abierto el 2026-08-02. Objetivo: que Héctor pueda charlar mucho rato sin
> degradarse, con la ventana de contexto bien dimensionada y la compactación
> disparando cuando toca. Este documento se escribe DESPUÉS de medir, no antes.

## Lo que ya está medido

### El modelo tiene diez veces más ventana de la que usamos

`config.json` de Qwen3-4B: `max_position_embeddings = 40960` (y con YaRN
llegaría a ~131k). Héctor corre con `HELIOS_CTX=4096`. El 4096 es una decisión
nuestra, no un límite del modelo.

Coste del KV: 36 capas × 8 cabezas KV × 128 × 2 × 2 bytes = **144 KiB/token**.

| Ventana | KV | En 8 GiB, con el modelo cargado |
|---|---:|---|
| 4.096 (hoy) | 0,56 GiB | de sobra |
| 8.192 | 1,12 GiB | holgado |
| 16.384 | 2,25 GiB | entra bien |
| 32.768 | 4,50 GiB | muy justo, probablemente no |

### La compactación ya existe, funciona y dispara sola

`helios_chat.cpp:1161`:

```c
compact_margin = min(1200, max_seq_len / 3);
if (cache_position() + compact_margin > max_seq_len)  /* compactar */
```

El margen está topado en **1200 tokens absolutos**. Consecuencia importante
para el dimensionado:

| Ventana | Dispara en | % de la ventana |
|---|---:|---:|
| 4.096 | 2.896 | 71 % |
| 8.192 | 6.992 | 85 % |
| 16.384 | 15.184 | 93 % |

Verificado en vivo: con ventana 4096 se observaron compactaciones a 3030,
3061 y 2977. Coincide.

### Una conversación de 30 turnos aguanta mejor de lo que creíamos

Medido con `tools/medir_conversacion.py` (guion fijo de 30 turnos, ventana
4096, `--no-distill`):

- **0 caracteres chinos en los 30 turnos**
- 4 turnos con alguna señal (13 %): **2 mudos**, 1 fuga de `</think>`, 1 bucle
- 3 compactaciones, todas correctas: la conversación siguió con sentido
  después de cada una (el turno 18 recordaba la primera pregunta y el 27
  recordaba la función de Python escrita nueve turnos antes)

## Lo que yo (Claude) había dicho mal, y la medida corrigió

1. **«La calidad se cae a los ~2000 tokens».** Salía de UNA sesión mala. Con
   guion fijo no se reproduce: 30 turnos hasta 3061 sin un solo carácter
   chino. La sesión catastrófica tenía algo particular —probablemente basura
   metida en el contexto por mis propias pruebas, que luego el modelo imita—
   y no es el comportamiento normal.
2. **«La compactación solo salta con el contexto lleno».** Falso: salta con
   1200 tokens de margen, o sea al 71 % con la ventana actual.
3. **«Subir la ventana empeoraría el chat».** Se apoyaba en el error anterior.
   Con margen fijo de 1200, subir la ventana alarga la conversación entre
   compactaciones — bueno si la calidad aguanta, malo si no. Es exactamente la
   pregunta abierta, no una objeción.

## Defectos reales que quedan, por frecuencia medida

| Defecto | Frecuencia | Dónde vive |
|---|---:|---|
| Turnos mudos | 2 de 30 (7 %) | `helios_chat`, rienda del pensamiento |
| Desgaste suave del idioma | no medido aún | modelo |
| Fuga de `</think>` como texto | 1 de 30 | `helios_chat` (mitigado en la UI) |

**Turnos mudos — causa localizada.** El flujo crudo del motor es literalmente
`' (pensando|corte) \n[17 tok (14 pensando) · pensamiento cortado]'`: ni una
letra. La rienda corta el pensamiento al agotar el techo, inyecta el cierre y
el modelo emite EOS sin hablar. El «rescate de turnos mudos» no cubre ese
caso. Además el techo se agota con 14-21 tokens en preguntas triviales.

**Desgaste suave del idioma.** El banco no lo detecta pero está ahí: «¡Hola
again!» (turno 6), «Soy aquí para ayudarte» (turno 26). Ni es chino ni es
bucle, así que las señales actuales lo dejan pasar. **Hasta que no se detecte,
no se puede arreglar ni afirmar que se arregló.**

## Fases

### F0 — terminar el metro *(en curso)*

`tools/medir_conversacion.py` ya mide chino, bucles, turnos mudos y fugas.
Falta:

- **detector de desgaste del idioma**: proporción de palabras inglesas en
  respuesta española, y concordancia rota. Sin esto el defecto más común no
  se ve.
- registrar las compactaciones como evento propio, y si el turno siguiente
  conserva un dato dicho antes del reseteo.

**Salida:** una curva de señales frente a posición de contexto, reproducible.

### F1 — ¿la calidad aguanta con ventana grande?

La única pregunta que decide el dimensionado. Mismo guion, tres ventanas:

```
HELIOS_CTX=4096  python3 tools/medir_conversacion.py --turnos 40
HELIOS_CTX=8192  python3 tools/medir_conversacion.py --turnos 40
HELIOS_CTX=16384 python3 tools/medir_conversacion.py --turnos 40
```

Con 16384 la compactación no salta hasta 15184, así que la conversación
recorre territorio nunca probado. Si las señales se disparan a mitad de
camino, la conclusión es que el margen fijo de 1200 se queda corto y hay que
compactar por umbral de calidad; si aguanta, la ventana grande es ganancia
limpia y encima con menos reseteos.

**Barrera:** promover la ventana grande solo si la tasa de señales no empeora
frente a 4096 en el mismo guion.

### F2 — arreglar los turnos mudos *(requiere Hector-engine, coordinar con GPT)*

Dos candidatos, en orden de coste:

1. **Rescate real:** si tras el corte de rienda el turno cierra sin texto
   visible, reintentar la generación ya con el pensamiento cerrado en el KV.
2. **Techo con suelo:** que una pregunta trivial no reciba un techo de
   pensamiento tan bajo que se agote en 14 tokens.

**Barrera:** cero turnos mudos en el guion de 40, sin perder velocidad ni
cambiar el resto de respuestas.

### F3 — HEXOS dimensiona la ventana *(idea de Andrés)*

El cuerpo es quien sabe qué hardware hay, así que es su trabajo. Reglas:

- consultar VRAM libre **antes** de cargar, y calcular el KV a 144 KiB/token
  con los parámetros reales del HNF, no con constantes;
- dejar un margen de seguridad para el resto del escritorio;
- **topar por lo que F1 demuestre que la calidad aguanta.** El objetivo no es
  la ventana máxima que cabe, sino la mayor ventana útil. Reservar 32k porque
  entra, si la calidad muere a los 8k, es darle a Héctor más sitio para
  desvariar;
- mostrar en el panel la ventana **conseguida**, no la pedida.

**Barrera:** en la máquina de Andrés elige >= 8192 sin dejar la VRAM al borde,
y degrada con elegancia si otro proceso ya ocupa la tarjeta.

### F4 — memoria a largo plazo

Solo cuando lo anterior esté estable. La compactación destila al diario y el
diario se carga al arrancar: son la misma memoria a dos escalas. Con ventana
grande se puede re-prefilear más resumen tras compactar, o sea que Héctor
recordaría más en vez de arrancar casi de cero.

Pendiente concreto ya detectado: el diario tiene entradas tóxicas (una
transcripción cruda y un bucle guardado literal del 2026-08-01). Una
transcripción en el diario no es un dato: es un ejemplo que el modelo imita.
Usar siempre `--no-distill` mientras se desarrolla.

## Reglas

1. Ninguna afirmación sobre calidad sin el guion fijo detrás. Una sesión suelta
   no es una medida — esta campaña ya empezó con tres conclusiones mías falsas
   por saltarme esto.
2. Un cambio por vez, contra el mismo guion y la misma ventana.
3. Los arreglos del motor esperan a que GPT termine visión. Mientras tanto,
   solo se mide y se mitiga en la UI.
4. Nada de subir la ventana «porque cabe»: primero F1.
