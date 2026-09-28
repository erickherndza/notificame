# Resumen — Notificaciones push al TB39

## Resultado de las pruebas

| App | Resultado | Causa confirmada |
|---|---|---|
| WhatsApp Business (`com.whatsapp.w4b`) | ❌ No llegó al reloj | Hardcodeado en el código: la app solo reconoce el paquete `com.whatsapp` (WhatsApp normal). Confirmado con logcat: el mensaje llegó al teléfono (74 líneas de actividad) pero `NotifyService` nunca lo procesó. |
| SMS (vía CallApp) | ❌ No llegó al reloj | Hardcodeado a `com.android.mms`. Tu app de SMS por defecto es `com.callapp.contacts` (confirmado con `dumpsys role android.app.role.SMS`). |
| Instagram (`com.instagram.android`) | ❌ No llegó al reloj (4 intentos) | **Sin explicación confirmada.** El código SÍ soporta Instagram explícitamente (paquete coincide, toggle estaba en ON), y aun así no llegó nada al reloj. Esto sugiere un problema más profundo que el simple filtro de paquetes — ver hipótesis abajo. |
| Llamadas entrantes | ❌ No va a funcionar nunca (con este código) | Doble bloqueo: permiso `READ_PHONE_STATE` no concedido, y el código solo vibra si `deviceInfoData.isBracelet()==true` — tu TB39 se reporta como `WatchType.RECTANGLE` (reloj, no pulsera), así que ese chequeo siempre da `false`. |

## Cómo se investigó

Todo esto se determinó leyendo el **código fuente real** de la app
`com.sinophy.smartbracelet` (decompilado con `jadx` desde el APK sacado del
teléfono con `adb`), específicamente:

- `com/sinophy/smartbracelet/service/NotifyService.java` — filtro de apps por
  nombre de paquete exacto (línea ~85 para WhatsApp, ~104 para SMS)
- `com/sinophy/smartbracelet/helper/CallStateMonitor.java` — lógica de
  llamadas entrantes, requiere `isBracelet()`
- Confirmado en vivo con `adb logcat`, `adb shell dumpsys notification`,
  `adb shell dumpsys role`, `adb shell dumpsys package` y `adb shell dumpsys
  bluetooth_manager`.

## Hipótesis para el fallo de Instagram (caso sin explicación)

A diferencia de WhatsApp/SMS, el código de Instagram debería funcionar. Posibles causas no descartadas:

1. **`SmartBraceletBleManager.INSTANCE.isConnected()` da `false`** en el
   momento de la notificación, aunque el sistema operativo (`dumpsys
   bluetooth_manager`) muestre la conexión BLE activa — es un estado interno
   de la app que puede desincronizarse.
2. El comando `MESSAGE_PUSH` (opcode `0xA0`) sí se envía por BLE, pero **el
   reloj lo recibe y no hace nada visible** (firmware del TB39 no soporta
   bien ese comando, o requiere un formato de `MessageData` distinto al que
   arma la app).
3. Algún otro chequeo interno (ej. Modo No Molestar, un límite de
   frecuencia/rate-limit, o el estado `messageReminderSwitch` que vimos
   apagado/encendido en `device_switch`) está bloqueando la notificación
   antes de llegar al BLE.

**La forma más rápida de confirmar cuál de las 3 es**: repetir la captura
`btsnoop_hci.log` (como hicimos el primer día) mientras se dispara una
notificación de Instagram, y con `parse_btsnoop.py` revisar si aparece un
paquete `Write Command` con opcode `0xA0` dirigido al reloj. Si aparece →
el problema es del firmware del reloj (opción 2). Si no aparece → el
problema es de la app antes de llegar al Bluetooth (opción 1 o 3).

## Alternativas si se confirma que la app oficial no sirve para esto

Ya tenemos el protocolo BLE completo del TB39 documentado y funcionando
(`tb39_client.py`, `tb39_protocol_decoded.txt`), así que hay varias rutas
independientes de la app oficial:

### 1. Parchear la app oficial (la más simple, no requiere programar de cero)
Editar el smali/bytecode de `NotifyService.class` para agregar
`com.whatsapp.w4b` y `com.callapp.contacts` a la lista de paquetes
reconocidos, volver a firmar el APK e instalarlo. Herramientas: `apktool`
(decompilar/recompilar a smali) + `apksigner` o `uber-apk-signer`. Riesgo
bajo, cambio quirúrgico de 2-3 líneas.

### 2. App/servicio propio mínimo (la más flexible)
Un `NotificationListenerService` propio (Android, Kotlin/Java) que:
- Escuche notificaciones de CUALQUIER app (sin la lista hardcodeada)
- Arme el comando `MESSAGE_PUSH` usando la lógica que ya tenemos en
  `tb39_client.py` (`generate_command(0xA0, ...)`)
- Escriba directo a la characteristic `0xFF13` del reloj

Esto requeriría convertir `tb39_client.py` a Kotlin/Java + Android BLE APIs
(bastante directo, ya que toda la lógica del protocolo está resuelta), y
compilar un APK mínimo con Android Studio o Gradle desde la terminal.

### 3. Automatización con Tasker/MacroDroid (si soportan BLE GATT write)
Algunas apps de automatización tienen plugins de BLE genérico. Con el
frame builder que ya documentamos, se podría configurar una tarea que
escriba bytes crudos a `0xFF13` cuando llegue una notificación — sin
programar nada, pero depende de que el plugin de turno permita escribir
bytes arbitrarios (no todos lo permiten).

## ACTUALIZACIÓN — parche instalado y probado en el reloj real (2026-08-23)

Después de mucha pelea con las protecciones de instalación de MIUI/HyperOS
(bloqueo de instalaciones por adb, conflicto de firma al reemplazar la app
oficial, y falta de splits), se resolvió así:

1. Se fusionaron las 4 partes del APK (base + arm64_v8a + es + xxhdpi) en
   un solo APK universal con `apktool` (evita el problema de "split APKs").
2. Se cambió el `package` en el manifiesto a `com.sinophy.smartbracelet.patched`
   (en vez de `com.sinophy.smartbracelet`) para que Android no lo trate como
   una versión falsificada de la app oficial y active el bloqueo de
   seguridad de Play Protect.
3. Se firmó con una keystore propia y se instaló tocando el APK directo
   desde el explorador de archivos del teléfono (adb install seguía
   bloqueado por MIUI incluso con todos los ajustes de seguridad
   desactivados — solo funcionó `adb install -r` para actualizaciones
   *posteriores*, una vez ya instalada con la misma firma).

### Resultados de las pruebas reales

- ✅ **WhatsApp Business**: los mensajes llegan al reloj correctamente
  (parche de `NotifyService.smali`: cambiar el paquete comparado de
  `com.whatsapp` a `com.whatsapp.w4b`).
- ✅ **Llamadas entrantes**: el reloj timbra y se puede **contestar desde
  ahí** (parche de `CallStateMonitor.smali`: se quitó el chequeo
  `isBracelet()==true` que bloqueaba el aviso porque el TB39 se reporta
  como `WatchType.RECTANGLE`, no como pulsera).
- ❌ **Nombre/número de quien llama**: confirmado imposible — el comando
  `startIncomingCall()` no lleva ningún dato, es una limitación real del
  protocolo/firmware, no arreglable desde la app.
- ⚠️ **Bug crítico**: al **borrar/deslizar un mensaje de WhatsApp
  directamente en la pantalla del reloj**, el reloj se resetea de fábrica
  (pierde el vínculo, hay que volver a emparejar). Se investigó a fondo:
  - Se descartó como causa un desborde del campo de longitud de 1 byte del
    protocolo (se agregó un truncado de seguridad a 200 bytes en
    `UWatchBleManager.pushMessage()`, pero el crash persistió igual).
  - Se confirmó que la app **no tiene ningún manejador de respuesta para
    el comando `MESSAGE_PUSH`** en `UWatchDispatch` — es decir, la app no
    manda nada de vuelta al reloj en ese momento. El bug es 100% interno
    del firmware del reloj, sin ninguna vía de arreglo posible desde el
    lado de la app Android.
  - **Workaround**: no borrar los mensajes de WhatsApp desde la pantalla
    del reloj — leerlos/ignorarlos ahí y revisar el mensaje completo desde
    el teléfono. Recibir el mensaje funciona perfecto; es específicamente
    el gesto de borrar en el reloj el que dispara el reset.
- **Nota operativa**: después de cada apertura/actualización de la app,
  hay que asegurarse de que quede "conectada" al reloj (se desconecta el
  BLE cuando el proceso de la app se cierra) para que sigan llegando las
  notificaciones.

## Archivos relevantes del proyecto
- `tb39_gatt_map.txt` — mapa GATT del reloj
- `tb39_protocol_decoded.txt` — protocolo completo decodificado del SDK
- `tb39_client.py` — cliente Python funcional (lee batería, pasos, perfil, etc.)
- `parse_btsnoop.py` — parser de capturas HCI para diagnosticar en vivo
- `smartbracelet_src/` — código fuente decompilado completo de la app
