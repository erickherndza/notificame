# notificame

Ingeniería inversa del protocolo BLE del smartwatch **TB39** (app oficial
`com.sinophy.smartbracelet` / SDK `com.uwatch.sdk`) e investigación para
llevar notificaciones y control de asistencia ("pase de lista") al reloj.

Proyecto personal de interoperabilidad sobre un dispositivo propio: se
analizó el protocolo Bluetooth Low Energy del reloj, se documentó por
completo y se construyó un cliente propio para hablar con él sin depender
de la app oficial.

## Objetivo

La app oficial del TB39 no reenvía al reloj las notificaciones que interesan
(WhatsApp Business, SMS con apps alternativas, etc.) porque tiene la lista de
paquetes *hardcodeada*. El objetivo fue entender por qué y abrir vías propias
para enviar avisos al reloj, y de ahí extenderlo hacia una app de **pase de
lista** para profesores.

## Qué contiene este repositorio

### Código (Python)
- **`tb39_client.py`** — cliente BLE funcional: lee batería, pasos, perfil y
  arma comandos del protocolo (incluye `MESSAGE_PUSH`, opcode `0xA0`).
- **`parse_btsnoop.py`** — parser de capturas HCI (`btsnoop_hci.log`) para
  diagnosticar en vivo qué se envía por Bluetooth.
- **`scan_watch.py`** — escaneo/descubrimiento del dispositivo por BLE.
- **`sniff_watch.py`** — utilidad de sniffing del tráfico GATT.

### App
- **`pase-de-lista/index.html`** — prototipo web de pase de lista
  (Multimedia, 22 estudiantes) para usar desde el teléfono; ver
  `pasedelista.md` §7.

### Documentación de protocolo
- **`tb39_protocol_decoded.txt`** — protocolo completo decodificado del SDK.
- **`tb39_protocol_capture.txt`** — captura anotada del intercambio real.
- **`tb39_gatt_map.txt`** — mapa de servicios y características GATT del reloj.
- **`tb39_live_capture.log`** / **`tb39_btsnoop_hci.log`** — capturas de
  referencia.

### Notas de investigación
- **`resumen.md`** — hallazgos de por qué las notificaciones no llegan, el
  parcheo del APK (smali) para habilitar WhatsApp Business y llamadas, y las
  pruebas reales sobre el reloj.
- **`pasedelista.md`** — diseño de la app "Pase de Lista" multi-reloj
  (Android teléfono como fuente de verdad + espejo Wear OS, y el TB39 como
  avisador pasivo), con la arquitectura, wireframes y especificación técnica.

## Hallazgos principales

- El TB39 se reporta como `WatchType.RECTANGLE` (reloj), no como pulsera, lo
  que rompe chequeos internos `isBracelet()` de la app oficial.
- El filtro de notificaciones está *hardcodeado* (`com.whatsapp`,
  `com.android.mms`), por lo que WhatsApp Business y otras apps de SMS quedan
  fuera.
- Parcheando el smali de `NotifyService` y `CallStateMonitor` (y renombrando
  el paquete a `.patched` para esquivar el bloqueo de firma de MIUI/HyperOS)
  se logró: ✅ notificaciones de WhatsApp Business y ✅ llamadas entrantes
  contestables desde el reloj.
- Con el protocolo ya documentado, se puede enviar avisos de texto al reloj
  desde un cliente propio, sin la app oficial.

## Notas técnicas

Requiere Python 3.9+ y una pila BLE compatible (p. ej. [`bleak`](https://github.com/hbldh/bleak)).
Crea un entorno virtual e instala las dependencias antes de correr los scripts.

## Qué **no** se versiona

Por tamaño y por no redistribuir material de terceros, quedan fuera del repo
(ver `.gitignore`): el APK comercial y sus splits, las firmas, el árbol
decompilado de la app (`com.sinophy.smartbracelet`, regenerable con
apktool/jadx), las herramientas externas (apktool, jadx, JDK, keystores) y el
entorno virtual.

## Aviso legal

Trabajo de ingeniería inversa realizado sobre un **dispositivo propio** con
fines de interoperabilidad y aprendizaje. No incluye ni redistribuye el
software del fabricante. Úsese bajo tu propia responsabilidad.
