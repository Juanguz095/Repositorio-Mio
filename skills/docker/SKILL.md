---
name: docker-tutoria
description: Preparar los servicios de demostración conservando verificación TLS.
---
Trabaja desde la raíz del checkout existente; no crees worktrees salvo petición explícita. Lee la skill cloud-environment-runtime y su referencia Docker antes de ejecutar contenedores. Comprueba el socket administrado. Conserva proxy y certificados; nunca desactives TLS. Usa el secreto de build proxy_ca para pip. Configura tokens distintos fuera del repositorio. Ejecuta docker compose build y docker compose up -d. Comprueba /health y el flujo de aprobación; un puerto abierto no demuestra funcionamiento. No expongas el prototipo a Internet.
