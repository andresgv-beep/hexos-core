# Prueba aislada de LM Studio

Adaptador experimental de Chat Completions. Reutiliza Agent, catálogo, validadores,
ejecutores y HTML de HexOS; no modifica su código ni el de Héctor. No instala paquetes.

## Arranque

Activa el servidor local de LM Studio (Developer). Desde la raíz del repositorio:

```bash
python3 experiments/lmstudio/run.py --probe
python3 experiments/lmstudio/run.py --model 'IDENTIFICADOR_DEVUELTO_POR_PROBE'
```

Abre http://127.0.0.1:8081/. Si el servidor anuncia un único modelo, se puede omitir
`--model`. Otro puerto de LM Studio: `--endpoint http://127.0.0.1:PUERTO/v1`.
El adaptador acepta únicamente HTTP de loopback, ignora proxies y rechaza redirects.
No arranca, descarga, carga ni detiene modelos: LM Studio gestiona la inferencia.
Conviene comprobar memoria disponible si Héctor conserva su modelo en GPU.

Los datos de prueba se crean en `runtime/lmstudio-experiment/`, nunca en el almacén
habitual. Por tanto inicialmente no hay nombres de dispositivos ni historial real,
perfil HERA. Por defecto tampoco hay sesión SSH del NAS; la herramienta devuelve sesión no disponible.
La lectura pasiva de red sí consulta el equipo; los nombres e informes que se guarden
quedan en el almacén experimental. El acceso opcional al NAS se describe a continuación. El chat habitual en 8080 permanece independiente.

Prueba sugerida: «Consulta el inventario guardado»; después «Busca las IP locales».
Comprueba eventos de herramientas y respuestas, no solo el texto del modelo.

Ctrl+C detiene exclusivamente el chat experimental. Para retirar esta prueba basta
con eliminar esta carpeta y, si no interesa conservarlos, sus datos experimentales.

## Contrato y límites

Usa `/v1/models` y `/v1/chat/completions`, con catálogo enviado como `tools`.
LM Studio debe devolver llamadas estructuradas `tool_calls`: no se ejecuta código
extraído del texto. Se validan todas las llamadas de una respuesta antes de devolver
la primera al ejecutor, preservando ids y resultados de cada llamada. Una generación
truncada no ejecuta herramientas. Se conserva el límite de seis herramientas de Agent.
El aviso previo usa el contenido del modelo si está presente; si falta, Agent conserva
su aviso genérico. No se añade una generación suplementaria en esta prueba.

Se reutiliza deliberadamente la política conversacional actual para comparar modelos;
no se atribuye cualquier mejora a los pesos sin controlar también el contexto.
El razonamiento debe llegar separado de `content`; bloques think incrustados se rechazan.
No hay streaming; el aviso se publica tras recibir la llamada y antes de ejecutarla.
No se ha certificado la compatibilidad real del Qwythos hasta conectarlo y probarlo.

Validación local:

```bash
python3 -m unittest experiments.lmstudio.test_adapter -v
```

API oficial: https://lmstudio.ai/docs/developer/openai-compat/tools

## Sesión NAS opcional

Tras autorizar la prueba SSH, se añadió `--nas-session` al lanzador. Solo redirige
`nas.read` al broker de lectura ya abierto para `runtime/workspace`; no copia
contraseñas, no comparte el inventario y no modifica el agente habitual. Los
argumentos del modelo siguen limitados a section/disk y los comandos del broker
siguen siendo fijos. Sin la opción, conserva el aislamiento original.

```bash
python3 experiments/lmstudio/run.py --model qwythos-9b-claude-mythos-5-1m --nas-session
```

La sesión puede caducar: en ese caso hay que abrirla localmente de nuevo.

### Prueba real SSH (2026-09-12)

Acceso de lectura validado con el broker existente. Primera petición general:
solicitó system+storage y después diagnosis+kernel+SMART de tres discos (7 llamadas).
Se ejecutaron seis y Agent detuvo el turno sin respuesta final; había consultas
redundantes porque diagnosis ya reúne kernel/SMART. Segunda petición, explícitamente
limitada a diagnosis: una llamada y respuesta final. Identificó ata1/sda y mantuvo
la causa cable/controlador/disco como hipótesis. Omitió los contadores de sectores y
la limitación SMART del NVMe; la frase «PASSED en todos» resulta demasiado amplia.
La fluidez no equivale todavía a exhaustividad diagnóstica. Resultados privados:
`runtime/lmstudio-experiment/nas-trial*.json` y eventos de la base experimental.
