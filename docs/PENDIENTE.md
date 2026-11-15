# Pendiente

Lista viva, apuntada el 2026-11-14. Lo que se cierre se quita de aquí.

## Chat

- **Que sepa qué modelo es.** En su prompt no hay dato del modelo ni de sus parámetros; a
  «¿qué modelo eres?» contesta lo genérico de Google.
- **El tono tras un reinicio.** Arranca con el contexto limpio y tarda en coger rodaje.
- **El clasificador de registro se cuela a veces en «técnico»** con preguntas cortas de juego
  («¿Vale espada? ¿Daga?»). Apenas se nota.
- **Ideas de orquestación del 26B sin hacer:** recordar notas por su cuenta cuando vienen a
  cuento, y más registros.
- **`[[matrix]]` a rachas:** el modelo se copia a sí mismo; lo frena el tope de la interfaz.

## Agente

- **Proyectos, fase 4** (`PROYECTOS_CON_FICHA_PLAN.md`): hecha entera el 14/11 (leer, escribir con
  aprobación, memoria JSON y ejecutar en jaula). **Por comprobar con el 26B y en pantalla:** montar
  un proyecto desde cero, la tarjeta de varios ficheros, pasar pruebas y remontar tras un corte.
- **Fichas de técnica** (`TECNICAS.md`): hechas el 15/11 con cinco de serie. Por medir con el
  26B, y falta que Helios proponga fichas nuevas con lo que aprende, para aprobarlas.
- **Que vea lo que dibuja:** diseña ventanas a ciegas (15/11, la calculadora de PyQt6 salió
  descolocada tres veces). Con la jaula puede pintar la ventana fuera de pantalla y guardar una
  captura; falta una herramienta para que mire esa imagen.
- **Cambiar por trozos de memoria:** el 26B manda como `old` el fichero entero tal como lo
  recuerda; si no coincide con el disco falla, relee y repite (cuatro veces el 15/11, medio
  minuto cada una).
- **Ejecutar, lo que falta:** la gráfica dentro de la jaula (CUDA) y un entorno por proyecto
  (venv) para bibliotecas que no estén en apt.
- **Borrar y renombrar ficheros** del proyecto: no hay.
- **El E4B no encadena pasos:** a «arréglala» lista, dice que necesita leer y cierra el turno.
- **Seguir la pista del código:** comprobado con el 26B el 14/11 (ocho lecturas en un turno, 2.053
  líneas, y dice exacto lo que ha leído). Le queda distinguir un interruptor de pruebas
  (`HERA_SABOTAJE`) de un riesgo real. El E4B lee el fichero entero pero no salta a quien lo llama.
- **Un modelo por ventana:** que Chat y Agente carguen cada uno el suyo al cambiar. Candidatos de
  código para el Agente, sin probar: Qwen3-Coder-30B-A3B, Laguna XS 2.1, North Mini Code (MoE de
  ~30B que caben en 23 GB). Primer paso: mirar su `config.json` contra lo que soporta el motor.
- **Paginar expertos de un MoE grande:** idea de Andrés; antes de construir, registrar qué expertos
  usa el 26B y simular la tasa de acierto de una caché. Con 32 GB de RAM el techo son ~49 GB.
- **Ventanas Chat y Agente:** los cuatro cambios pedidos el 10/11 (separar las ventanas,
  encadenar la búsqueda de apps, chat más libre, agente más directo).
- De la ficha: el resumen de intención escrito por el modelo, la ficha como fichero en la
  carpeta para el uso remoto, y borrar o renombrar un proyecto.

## Medir

- **Informe del bench de tareas y herramientas:** sin escribir; los datos crudos están en el
  sobremesa.
- **Reserva de VRAM del 12B** en el sobremesa, para la ventana automática.
- **Verificar lo de noviembre con el 12B, Qwen y DeepSeek:** solo está visto con el E4B y el 26B.
- **Seis ficheros de pruebas que no ejecutan ninguna:** chats, protocolo, reflexión, relevo,
  ruta de memoria y sesiones del runtime. Salen como fallo en la batería.
- Proyectos con historial real y largo, y el banco de 31 frases del selector tras tocar su guía.

## De Andrés

- Las dos carpetas viejas de `~/.helios`: sin aprobar su borrado.
- La rama remota `herramientas-por-cajones`: no borrar sin preguntar.
