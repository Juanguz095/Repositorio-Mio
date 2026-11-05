# TutorIA en Windows con el n8n que ya tienes

1. Abre Docker Desktop y conserva tu contenedor `tutoria-n8n-local`.
2. Extrae el ZIP completo del proyecto a una carpeta.
3. Haz doble clic en `INICIAR_TUTORIA.cmd`. La primera vez Docker descargará las dependencias y construirá la API.
4. Espera hasta ver `API lista` y `Conexion n8n -> API: OK`.
5. Abre `http://localhost:8000/health` en el navegador. Debe mostrar `status: ok` y `mode: synthetic-demo`.

El inicio conserva tu contenedor y volumen de n8n. Conecta la API a la misma red Docker, con el nombre `api`, para que las URLs `http://api:8000/...` de los workflows importados funcionen. Usa almacenamiento persistente para los datos de la API y no sobrescribe ejemplos existentes. Ejecuta una importación sintética idempotente de comprobación: 30 casos pendientes, sin aprobación automática.

Las tres claves de roles se generan en tu PC y se guardan en `%LOCALAPPDATA%\TutorIA\api.env` con acceso restringido a tu usuario. No compartas ese archivo ni pegues sus valores en el chat. La clave del operador, con su prefijo `Bearer`, queda en el portapapeles; la del revisor no se copia a n8n.

## Credencial del operador en n8n

En el nodo HTTP que llama a TutorIA:

1. Authentication: **Generic Credential Type**.
2. Generic Auth Type: **Header Auth**.
3. Crea una credencial llamada **Operador TutorIA**.
4. En **Name** escribe `Authorization`.
5. En **Value** pega el contenido del portapapeles con Ctrl+V.
6. Guarda la credencial y el workflow.

Los nodos Webhook requieren además una credencial propia para autenticar su entrada. El formulario requiere su propia Basic Auth. Esas credenciales son distintas de la del operador y de la del revisor. No actives un workflow hasta completar los nodos que tengan credenciales pendientes.

## Repetir el inicio

Puedes ejecutar de nuevo `INICIAR_TUTORIA.cmd`: reutiliza las claves, los datos y el contenedor de la API. No borra n8n ni sus workflows. Detiene el proceso con un error si encuentra recursos con los mismos nombres que no pertenecen a este instalador. No actualiza ni reemplaza silenciosamente un contenedor API existente.

El inicio local usa el modo determinista y datos sintéticos. La ejecución de un LLM local y la evaluación con históricos reales son pasos separados descritos en README.md.

## Límites de comprobación

Se comprobó la sintaxis PowerShell y se ejecutó el mismo inicio con PowerShell en Linux, incluyendo construcción Docker, semilla, API HTTP y conexión desde n8n. La inicialización se repitió sin sobrescribir datos. La rama específica de ACL/portapapeles de Windows necesita confirmación en tu PC.

## Arreglo de "No se pudo comprobar la red de n8n"

El iniciador antiguo usaba plantillas Docker con comillas que Windows PowerShell podia quitar. La version corregida solicita JSON y comprueba las propiedades dentro de PowerShell. Se reprodujo el fallo con argumentos Legacy y se comprobo el inicio completo corregido: primera conexion, reinicio Legacy y modo Standard.

Descarga el ZIP actualizado y extraelo en otra carpeta. Ejecuta `INICIAR_TUTORIA.cmd` desde esa carpeta nueva. Las claves se reutilizan desde `%LOCALAPPDATA%\TutorIA\api.env`; los contenedores y volumenes existentes se conservan. No hace falta reinstalar n8n ni volver a importar sus workflows.

## Celular Android

La APK de demostracion y las instrucciones USB estan en [mobile/LEEME_CELULAR.md](mobile/LEEME_CELULAR.md). La conexion requiere una PC con la API encendida y un cable USB de datos.
