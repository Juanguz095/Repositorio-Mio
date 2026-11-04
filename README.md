# TutorIA — prevención de la deserción (prototipo UNMSM)

Captura un lote, limpia los datos, entrena mediante código y genera casos pendientes de revisión humana. Android consulta los casos aprobados ordenados por probabilidad. La configuración local usa datos sintéticos. Incluye SQLite, formulario de n8n, evaluación temporal y un planificador LLM local opcional. No está conectada al SUM ni representa un sistema institucional de producción.

## Usar en tu computadora Windows

Si ya tienes n8n local y los workflows importados, sigue [LEEME_WINDOWS.md](LEEME_WINDOWS.md) y abre `INICIAR_TUTORIA.cmd`. El inicio conserva n8n, genera claves privadas locales y conecta la API con el nombre `api`. No requiere Python instalado en tu PC; sí Docker Desktop y PowerShell.

## Ejecutar la API

Desde la raíz del checkout existente:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample.py
# Definir OPERATOR_TOKEN, REVIEWER_TOKEN y MOBILE_TOKEN en el entorno:
# tres valores distintos, privados y aleatorios; no guardarlos en Git.
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

El generador protege los archivos existentes: usa `--force` únicamente si deseas reemplazar los cuatro ejemplos generados.

`GET /health` comprueba disponibilidad; `/docs` permite probar los endpoints usando Authorize. SQLite y las entradas de ejemplo viven en `data/`, ignorado por Git. `TUTORIA_DB` permite elegir la base; `TUTORIA_DATA` cambia el directorio autorizado del harness.

## Flujo de captura y predicción

1. **Captura:** n8n recibe JSON o Excel y dispone de un formulario HTML autenticado y un conector SQLite de solo lectura con vistas académicas. Las observaciones del formulario se acumulan por periodo antes de puntuarlas. No se incluyen credenciales ni una conexión a una base institucional.
2. **Limpieza:** `DataAgent` orquesta herramientas del harness. Normaliza encabezados (espacios, mayúsculas y tildes), formatos numéricos, coma decimal y porcentajes de asistencia. Elimina duplicados tras normalizar, rechaza conflictos y valores fuera de rango. Los nulos de las variables predictoras se imputan dentro del pipeline, ajustado solo con entrenamiento.
3. **Entrenamiento y predicción:** el código entrena una regresión logística con periodos históricos anteriores al último. El último periodo histórico queda reservado para evaluación. Los alumnos a evaluar no necesitan etiqueta y deben pertenecer a periodos posteriores a todo el histórico. No se reajusta el modelo con la cohorte de evaluación.
4. **Revisión:** la API guarda probabilidades, detalle académico e informe/traza del lote. Todos los casos quedan pendientes. El revisor aprueba o rechaza cada caso.
5. **Android:** consulta la API y muestra únicamente aprobados, de mayor a menor probabilidad, con detalle e historial de revisión. La entrega es por consulta al pulsar Actualizar; no hay push.

### Contrato de datos

Cada fila requiere `alumno_id`, `periodo` (entero positivo ordenable), `asistencia` (0–1 o texto como `75%`), `promedio` (0–20), `creditos_aprobados` (0–40). Se añaden `matriculado` y `pagos_al_dia`, indicadores 0/1 observados antes del resultado; aceptan nulo. Nulo significa sin información o no aplicable, nunca deuda o falta de matrícula. Para compatibilidad, si faltan estas columnas se conservan como nulas y el informe identifica las variables no disponibles en el entrenamiento. Los identificadores se tratan como texto; en Excel deben guardarse como texto para conservar ceros iniciales.

El conjunto `history` requiere además `deserto` binario 0/1 y al menos dos periodos, con ambas clases tanto en entrenamiento como en evaluación. `students` contiene las observaciones futuras a puntuar. Cada conjunto acepta entre 1 y 10 000 filas. Se descartan campos ajenos al contrato. Los indicadores nuevos forman parte del pipeline; no se leen montos de deuda ni se inventan obligaciones de pago. No usar la matrícula futura que define el abandono como variable predictora.

**JSON:** el operador hace `POST /ingest/records` con:

```json
{
  "import_id": "lote-20242-001",
  "history": [{"alumno_id":"SYN-001","periodo":20231,"asistencia":0.8,"promedio":13,"creditos_aprobados":20,"matriculado":1,"pagos_al_dia":1,"deserto":0}],
  "students": [{"alumno_id":"SYN-900","periodo":20242,"asistencia":"75%","promedio":"12,5","creditos_aprobados":18,"matriculado":1,"pagos_al_dia":null}]
}
```

La estructura anterior ilustra el contrato; para ejecutar un lote con suficientes periodos y clases usa `data/records.json`, generado por `python scripts/make_sample.py`.

**Excel:** el operador hace `POST /ingest/excel` con:

```json
{"import_id":"excel-20242-001","history_path":"history.xlsx","students_path":"students.xlsx"}
```

Solo se leen archivos `.xlsx` dentro de `data/raw`; no se aceptan rutas externas. En Compose ese directorio se monta desde el host en modo lectura. El webhook recibe nombres de archivos ya disponibles, no archivos adjuntos ni rutas del ordenador del usuario. La API Docker usa UID 10001: el directorio y los Excel deben ser legibles por ese usuario. El generador prepara los permisos de los nuevos ejemplos sintéticos; no cambies indiscriminadamente permisos de carpetas con otros datos.

`import_id` es obligatorio: repetir la misma petición devuelve el mismo lote; reutilizar el ID con contenido distinto devuelve 409. Para una nueva captura usa un ID nuevo, estable en los reintentos. El operador puede recuperar métricas, calidad y traza con `GET /batches/{id}`.

### Roles y aprobación

- **Operador / n8n:** `OPERATOR_TOKEN`, permite importar y consultar informes. No aprueba casos.
- **Revisor humano:** `REVIEWER_TOKEN`, permite `GET /review`, `GET /review/{id}` (detalle académico e historial) y `POST /review/{id}` con `{"approve":true,"note":"Seguimiento acordado con el tutor"}`. `false` rechaza. No entregar esta credencial al agente ni a n8n.
- **Móvil:** `MOBILE_TOKEN`, permite `GET /cases`, `GET /cases/{id}` y `GET /cases/{id}/history`. Los casos pendientes o rechazados no se exponen.

`POST /demo/run` mantiene la demo sintética original, que evalúa su último periodo y crea un lote nuevo en cada llamada. Ese endpoint no implementa idempotencia; para importaciones reintentables usa `/ingest/*`.

## n8n y Docker

```sh
python scripts/make_sample.py
# Exportar los tres tokens antes de usar Compose.
docker compose build
docker compose up -d
```

La API espera una respuesta saludable antes de iniciar n8n. Los volúmenes conservan SQLite y la configuración de n8n; `data/raw` se monta en modo lectura. El build mantiene TLS y usa el certificado indicado por `CODEX_PROXY_CERT` o el bundle del sistema. Los puertos quedan ligados a localhost. `NO_PROXY` y `no_proxy` incluyen los nombres internos `api` y `n8n`, para que la comunicación entre contenedores no pase por el proxy externo. `N8N_SECURE_COOKIE=false` solo facilita esta demo local; para un servidor remoto configura HTTPS y cookies seguras.

Importa `n8n/records.json` y/o `n8n/excel.json` en n8n:

1. En **Capturar lote**, selecciona una credencial Header Auth propia del webhook. Usa un token diferente de los tres roles de la API.
2. En **Procesar y dejar pendiente**, selecciona otra credencial Header Auth: encabezado `Authorization`, valor `Bearer <OPERATOR_TOKEN>`.
3. Activa el workflow y envía el JSON del contrato al webhook POST `tutoria-records` o `tutoria-excel`, con su autenticación. El nodo HTTP apunta a `http://api:8000/ingest/records` o `/ingest/excel` en la red de Compose.
4. El webhook devuelve el informe del lote pendiente. Revisa mediante `/docs` con la credencial de revisor; luego pulsa Actualizar en Android.

Para capturar desde una base de datos o formulario, añade sus nodos de origen y mapea sus resultados a `import_id`, `history` y `students` antes del nodo HTTP. La conexión específica depende de tu fuente. Evita guardar datos sensibles en el historial de ejecuciones; los workflows nuevos desactivan ese guardado. No incluyen credenciales ni se activan automáticamente.

`n8n/demo.json` conserva el disparador manual sintético. No requiere la importación de archivos.

## Agente, harness y skills

`TUTORIA_AGENT_MODE=rules` conserva el modo determinista disponible sin descargar modelos. `TUTORIA_AGENT_MODE=llm` activa el planificador Ollama local de `app/llm.py`. El LLM elige entre acciones válidas; el código ejecuta limpieza, entrenamiento y predicción. Nunca decide una probabilidad ni aprueba o publica casos.

El harness mantiene un máximo obligatorio de 10 llamadas y el planificador un máximo de 10 decisiones. Solo hay herramientas explícitas y rutas confinadas; se registran acciones y resultados. El LLM recibe cantidades de filas y progreso, sin filas, códigos de alumnos, celdas, rutas, SQL ni credenciales. El estado de ejecución impide entrenar antes de limpiar y comprobar la separación temporal. Una respuesta inválida detiene el lote; el modo LLM nunca cambia silenciosamente a reglas.

Para el modo local opcional:

```sh
docker compose --profile llm up -d --wait ollama
docker compose --profile llm exec ollama ollama pull qwen2.5:0.5b-instruct
TUTORIA_AGENT_MODE=llm docker compose --profile llm up -d api n8n
# Contra Ollama expuesto en localhost, inferencia real con datos sintéticos:
.venv/bin/python scripts/smoke_llm.py
```

La imagen oficial de Ollama se descargó y su API local arrancó correctamente, sin modelos instalados. El servidor mantiene TLS y el proxy al descargar pesos. La política de red actual bloqueó `registry.ollama.ai`: su acceso está propuesto en el borrador del entorno y requiere revisión/guardado/publicación. Guardar el borrador no aplica ese acceso. Si la descarga redirige a otro host, comprobar el destino concreto antes de añadirlo. La inferencia con pesos reales **todavía no está validada**; las pruebas del protocolo LLM usan respuestas simuladas y no se presentan como inferencia real. No requiere claves de un proveedor externo. Variables: `TUTORIA_LLM_URL` (solo localhost/ollama), `TUTORIA_LLM_MODEL` y `TUTORIA_AGENT_MODE`.

Skills locales: `skills/excel`, `skills/analisis`, `skills/docker`, `skills/orquestacion` y `skills/validacion`. Las skills describen el procedimiento; el código impone los límites. Una celda se trata como dato, nunca como instrucción.

## Fuentes locales: SQLite y formulario

Crea una base sintética separada, sin sobrescribir fuentes existentes:

```sh
.venv/bin/python scripts/make_source_demo.py
```

El conector lee las vistas `academic_history` (con etiqueta) y `academic_current` (sin etiqueta) desde `TUTORIA_SOURCE_DB`, por defecto `data/raw/source-demo.db`. Abre SQLite con `mode=ro` y `query_only`; usa consultas constantes, no SQL suministrado por el agente o la petición. El operador ejecuta `POST /sources/sqlite/run` con `{"import_id":"sqlite-001"}`. Un origen institucional deberá proporcionar estas vistas y permisos de lectura adecuados; no se simula una conexión que no existe.

Importa `n8n/sqlite.json` para exponer esa operación mediante el webhook autenticado `tutoria-sqlite`, asignando credenciales de webhook y operador como en el flujo JSON.

Importa `n8n/form.json` y asigna:

- Una credencial **Basic Auth** propia del formulario en los nodos Mostrar formulario y Recibir formulario.
- La credencial **Header Auth del operador** únicamente en Guardar observación.

Al activar el workflow, su ruta `/webhook/tutoria-form` sirve el formulario por GET y recibe el envío por POST. Usa únicamente localhost para HTTP; un despliegue remoto requiere HTTPS. El formulario captura identificación sintética, periodo, asistencia, notas, créditos, matrícula y pagos. La credencial de revisor no aparece en él.

Cada envío utiliza un `event_id`: repetirlo con el mismo contenido es seguro; cambiarlo con datos distintos devuelve 409. Se admite una observación inmutable por alumno/periodo y se rechazan conflictos. Capturar una observación **no crea ni publica un caso de riesgo**.

Cuando el periodo esté completo, el operador ejecuta `POST /sources/forms/run` con `{"import_id":"forms-001","periodo":20242}`. El histórico viene de SQLite y la cohorte de los formularios capturados. `n8n/forms-run.json` ofrece la misma operación en el webhook autenticado `tutoria-forms-run`. El lote resultante sigue pendiente de revisión humana. Los cinco workflows propagan el código de error de la API, en lugar de responder 200 vacío a entradas inválidas.

## Evaluación de históricos

```sh
.venv/bin/python scripts/validate_history.py \
  --history data/raw/history.xlsx \
  --protocol docs/protocol-synthetic.json \
  --output data/processed/evaluation-nueva.json
```

Admite CSV/Excel local y nunca sobrescribe un informe existente. Evalúa cohortes sucesivas entrenando solo con el pasado. Informa prevalencia, average precision, ROC AUC, Brier, precisión, sensibilidad y calibración. Si existe una columna `grupo`, agrega métricas por grupo con un mínimo de filas. Las cohortes insuficientes se marcan como omitidas y la última debe poder evaluarse.

Para un histórico real autorizado, copia y completa `docs/protocol-historical.example.json`: definición de deserción, horizonte, fecha de observación, matrícula y pagos, más la confirmación de autorización. El ejemplo se rechaza mientras conserve campos REEMPLAZAR o la autorización sea falsa. Las etiquetas futuras deben estar preparadas correctamente por el responsable del histórico; el código no las inventa ni certifica su procedencia. La separación temporal no demuestra que una variable no contenga información futura.

El informe distingue datos sintéticos de históricos declarados y no certifica eficacia institucional. **No se ha evaluado ningún histórico real:** el usuario aún no dispone de esa fuente. La validación ejecutada aquí corresponde a dos cohortes sintéticas.

## Android

Requiere Gradle 8.9, SDK 35 y JDK 17 o compatible con Gradle/AGP. No se incluye wrapper binario. Define `ANDROID_HOME` apuntando al SDK y ejecuta:

```sh
cd android
gradle --no-daemon --max-workers=2 :app:assembleDebug :app:assembleDebugAndroidTest
```

El APK queda en `android/app/build/outputs/apk/debug/app-debug.apk`. En un emulador Android, el servidor del host usa `http://10.0.2.2:8000`. HTTP solo está habilitado en debug; para un servidor remoto usa HTTPS. Introduce el token móvil en cada sesión; no se guarda. La app muestra probabilidad, lote, asistencia, promedio, créditos, matrícula, pagos e historial de aprobación. No incluye FCM ni biometría.

## Validación

```sh
. .venv/bin/activate
python -m pip check
python -m unittest discover -s tests -v
```

Las 18 pruebas pasaron en Python y dentro de la imagen Docker sin privilegios. Cubren API, fuentes, protocolo LLM acotado y evaluación temporal. Cubren Excel, formatos y rangos, separación temporal, restricciones del harness, importación, idempotencia y permisos de revisión y consulta móvil. Incluyen autorización mediante servidor HTTP real. También se generó y verificó la firma del APK debug con SDK 35 y Gradle 8.9. Pasó una prueba instrumentada real en Android 35: pendientes y rechazados ocultos, aprobados ordenados y detalle con matrícula, pagos e historial. La prueba de interfaz usa `scripts/smoke_android.py` contra un emulador dedicado y una API sintética temporal; sus evidencias se guardan en `data/processed/android-ui-*`.

La integración real de n8n pasó con JSON, Excel, SQLite y formulario HTML autenticado, propagación de errores, idempotencia, aprobación humana y consulta móvil de detalle e historial. La prueba reutilizable crea y elimina sus propios contenedores y red y usa tokens temporales:

```sh
docker build --secret id=proxy_ca,src="${CODEX_PROXY_CERT:-/etc/ssl/certs/ca-certificates.crt}" -t tutoria-demo:local .
docker pull n8nio/n8n:1.123.0
.venv/bin/python scripts/smoke_n8n.py
```

Prueba instrumentada de Android (una prueba JUnit real), tras compilar los dos APK y arrancar un emulador dedicado:

```sh
.venv/bin/python scripts/smoke_android.py --serial emulator-5554
```

Crea una API temporal y comprueba que se oculten pendientes y rechazados, que los aprobados estén ordenados por riesgo y que aparezcan matrícula, pagos y el historial. La prueba usa reenvío ADB para la API local (`127.0.0.1` dentro de Android), porque este entorno no proporciona ruta a `10.0.2.2`. Los tokens son temporales y se redactan en los resultados. Una ejecución sin pruebas o con fallos no se considera validación.

## Límites

La demo usa datos sintéticos. La herramienta de evaluación local admite un histórico previamente autorizado con su protocolo explícito; no se ha proporcionado uno en esta sesión. Las métricas sintéticas no prueban eficacia institucional. Antes de utilizar datos reales hay que acordar la definición y horizonte de deserción, evaluar calibración y rendimiento por grupos, ajustar umbrales a la capacidad de atención y establecer protección de datos y responsabilidades.

Para producción faltan autenticación individual y permisos por tutor, auditoría con identidad, registro persistente de modelos, migraciones y seguimiento de intervenciones. Los tokens compartidos solo sirven para la demostración local. No hay conexión institucional ni notificaciones push. El modo LLM local está implementado pero su ejecución con pesos reales sigue bloqueada por la descarga del modelo.
