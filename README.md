# TutorIA — prototipo UNMSM

Demo local con datos sintéticos, sin integración real al SUM. Python entrena el modelo; el harness permite herramientas deterministas sin necesitar un LLM ni enviar información a terceros. SQLite simplifica el prototipo. No representa un sistema institucional listo para producción.

## Ejecutar
Desde `/workspace/Repositorio-Mio` (o la raíz de este checkout):

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
# Definir OPERATOR_TOKEN, REVIEWER_TOKEN y MOBILE_TOKEN con valores distintos,
# privados y aleatorios en el entorno del proceso. No guardarlos en Git.
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Las cinco pruebas automatizadas pasaron tanto en el entorno Python como dentro de la imagen Docker tutoria-demo:local, ejecutada sin privilegios. Incluyen autorización mediante un servidor HTTP real. La integración de n8n y la compilación Android siguen pendientes de validación.

La documentación interactiva está en `/docs`. Usar el token adecuado con Authorize:
1. Operador: POST `/demo/run` genera 600 registros sintéticos, entrena con 400 y evalúa los 200 del último periodo; guarda esos 200 casos pendientes.
2. Revisor humano: GET `/review`, luego POST `/review/{id}` con `{"approve":true,"note":"Revisión del tutor"}`; false rechaza el caso. Esta credencial nunca se entrega al agente ni a n8n.
3. Móvil: GET `/cases` devuelve solo aprobados ordenados por probabilidad; GET `/cases/{id}/history` devuelve el historial autorizado.

Cada ejecución manual crea un nuevo lote; no programar reintentos automáticos: todavía no hay claves de idempotencia. El endpoint demo no acepta datos reales. El modelo se entrena en memoria por ejecución; no hay registro persistente de modelos.

## Excel y skills
`Harness('data').call('read_excel', path='entrada.xlsx')` lee `data/raw/entrada.xlsx`. Columnas: alumno_id, periodo numérico ordenable, asistencia 0–1, promedio 0–20 y creditos_aprobados 0–40. Para entrenar, añadir deserto binario y al menos dos periodos con ambas clases. `clean` elimina duplicados exactos y rechaza conflictos; la imputación ocurre dentro del pipeline entrenado solo con el pasado. Ver `skills/` para instrucciones reutilizables. El harness limita llamadas y rutas; no ejecuta shell ni llamadas arbitrarias. No se incorpora todavía un agente LLM.

## n8n y Docker
Importar `n8n/demo.json`; asignar una credencial Header Auth con `Authorization: Bearer <OPERATOR_TOKEN>`. El flujo manual llama al servicio api y deja los casos pendientes. La revisión ocurre mediante `/docs`; la app consulta los aprobados. No hay push ni conexión al SUM implementados.

`docker compose build` y `docker compose up -d` preparan API y n8n. El build usa el certificado indicado por CODEX_PROXY_CERT o el bundle del sistema. Mantener verificación TLS y proxy del entorno. Volúmenes conservan la base y n8n. La construcción requiere red operativa.

## Android
Abrir `android/` en Android Studio con JDK 17, SDK 35 y Gradle 8.9. No se incluye wrapper binario. El cliente nativo muestra casos aprobados, probabilidad, lote e historial. Introducir el token móvil en cada sesión; no se guarda. HTTP está habilitado solo en debug para el emulador (10.0.2.2). Para un servidor remoto usar HTTPS. Este cliente usa vistas nativas y un hilo de red simple; no implementa Compose/MVVM, FCM ni biometría. Compilación pendiente por falta de SDK/Gradle.

## Validación y límites
`python -m unittest discover -s tests -v` cubre Excel, limpieza, separación temporal, presupuesto de herramientas, rutas y aprobación/autorización.

La etiqueta sintética representa un resultado binario ilustrativo, no una definición oficial de deserción. Antes de usar registros reales: acordar horizonte y exclusiones (egreso, suspensión), validar temporalmente sin fuga de información, medir calibración y rendimiento por grupos, elegir umbrales según capacidad de atención y operar inicialmente en modo sombra. Las métricas sintéticas no prueban eficacia real.

Para producción faltan autenticación individual y permisos por tutor, auditoría con identidad, protección de datos, registro de modelos, migraciones PostgreSQL, idempotencia y seguimiento de intervenciones. Los tokens compartidos solo sirven para esta demostración local. No introducir información personal en esta demo.
