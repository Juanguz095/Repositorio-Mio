# Probar TutorIA en un celular Android por USB

La APK de esta carpeta es una compilacion de demostracion. Requiere Android 8 o posterior. La API sigue en tu computadora y la app recibe solo el token del rol movil. Las instrucciones usan USB para mantener la API ligada a localhost.

La version 0.2 muestra `TutorIA · 0.2` en el titulo y una etiqueta permanente **URL del servidor**. La direccion USB `http://127.0.0.1:8000` ya viene escrita. Toda la pantalla permite desplazarse y los campos tienen alturas explicitas para que la configuracion sea accesible al cerrar el teclado.

## 1. Instalar la app

Descarga `TutorIA-demo.apk` en el celular e instalala. Si lo descargaste en la computadora, copialo al celular por un cable USB de datos y abre el archivo desde Descargas/Archivos. Android puede pedir permiso para instalar desde ese navegador o administrador de archivos.

## 2. Preparar la conexion USB

Mantiene Docker Desktop y la API de TutorIA encendidos en la PC.

En el celular:

1. Abre Ajustes -> Acerca del telefono -> Numero de compilacion (en algunos modelos esta dentro de Informacion de software).
2. Tocalo siete veces para habilitar Opciones de desarrollador.
3. En Opciones de desarrollador, activa Depuracion USB.
4. Conecta el celular a tu PC con un cable que transfiera datos. Acepta el permiso de depuracion del equipo cuando aparezca.

En la PC descarga las herramientas oficiales de Google desde https://developer.android.com/tools/releases/platform-tools (SDK Platform-Tools para Windows). Extrae el ZIP, abre la carpeta que contiene `adb.exe`, escribe `powershell` en la barra de direcciones del Explorador y pulsa Enter.

Ejecuta:

```powershell
.\adb devices
.\adb -d reverse tcp:8000 tcp:8000
```

El celular debe aparecer como `device`. Si dice `unauthorized`, desbloquea el telefono y acepta su permiso de depuracion antes de continuar. `-d` selecciona el dispositivo USB, no un emulador. Si hay mas de un celular conectado, deja conectado solo el que vas a probar.

## 3. Configurar TutorIA

1. Abre TutorIA en el celular.
2. Debajo de la etiqueta **URL del servidor**, verifica la direccion `http://127.0.0.1:8000`. No anadas `/health` ni `/cases`. Si el teclado tapa algun control, cierralo y desplaza la pantalla.
3. Toca el campo **Token movil (solo memoria)** y dejalo enfocado, sin escribir nada.
4. En la misma ventana de PowerShell de la carpeta `adb.exe`, ejecuta:

```powershell
$linea = Get-Content "$env:LOCALAPPDATA\TutorIA\api.env" | Where-Object { $_ -like 'MOBILE_TOKEN=*' } | Select-Object -Last 1
$movil = ($linea -split '=',2)[1]
.\adb -d shell input text $movil
```

Esto escribe la clave movil en el campo enfocado del celular. No la publica ni usa las claves de operador o revisor. El token generado por el inicio local contiene caracteres seguros para este comando; no lo envies al chat.

5. En el celular, pulsa **Actualizar**. Debe aparecer el caso aprobado. Tocalo para ver datos academicos e historial.

La aplicacion mantiene el token solo en memoria: si se reinicia, vuelve a introducirlo. El reenvio USB puede necesitar repetirse al desconectar/reconectar o reiniciar el dispositivo. Puedes retirarlo con `.\adb -d reverse --remove tcp:8000`.

## Alcance comprobado

La app fue compilada, firmada y probada en un emulador Android 35 mediante reenvio ADB y una prueba instrumentada real. La instalacion y conexion en tu celular fisico requieren tu confirmacion. Esta APK no incluye claves de acceso y el conjunto de demostracion es sintetico; no demuestra eficacia institucional ni conexion al SUM.
