# Pase de Lista Multi-Reloj — Resumen de investigación (2026-08-23)

Fase de investigación/UX completada. Mañana arranca el desarrollo. Este
documento reúne todo lo decidido hoy para no repetir pasos.

## 1. Punto de partida

Documento original: `app-pase-lista-smartwatch.md` (guía de desarrollo
para una app **Wear OS nativa** de control de asistencia, sincronizando
con el backend **Tecnoauladom**). Ese documento sigue siendo válido tal
cual está escrito — pero **solo para un reloj Wear OS real**.

## 2. Verificación de factibilidad (hallazgo clave)

El objetivo es que la app funcione con **cualquier smartwatch**,
incluido el TB39 que ya reverse-ingenieramos en este mismo proyecto. Se
verificó explícitamente qué es posible con cada tipo de reloj:

| Capacidad requerida | Wear OS | BLE genérico (TB39) |
|---|---|---|
| Correr la app propia en el reloj | ✅ Sí | ❌ No — sin runtime de apps |
| Marcar P/A/E desde la muñeca | ✅ Sí (touch/corona) | ❌ No — sin canal de entrada real |
| Mostrar aviso de texto corto | ✅ Sí | ✅ Sí — vía protocolo `MESSAGE_PUSH` ya reverseado (servicio `0xFF12`, opcode `0xA0`, límite ~200 bytes, ver `resumen.md` y `tb39_protocol_decoded.txt` en este mismo proyecto) |
| Room DB + WorkManager en el reloj | ✅ Sí | ❌ No — el reloj no persiste nada |
| Dónde vive la lógica del documento (Fases 1-4) | En el reloj, sin cambios | Se muda entera al teléfono |

**Conclusión operativa**: el motor completo (Room, Retrofit,
WorkManager, UI de marcado) vive **siempre en el teléfono del
profesor**. El reloj es un accesorio opcional:
- Con **Wear OS**: segunda superficie interactiva completa, puede
  pasar lista por sí solo.
- Con un **reloj BLE genérico tipo TB39**: solo recibe avisos de texto
  pasivos (ej. "6to A: 3 sin marcar").

### Posibilidad explorada y descartada por ahora: "modo clicker" en el TB39

El TB39 tiene un puñado de botones físicos de fábrica que sí mandan una
señal de vuelta al teléfono (botón "buscar teléfono" = 1 clic, pantalla
de "control de música" = 6 botones distintos Play/Pausa/Prev/Next/Vol±).
Técnicamente se podría reutilizar uno de estos como "clicker ciego" de
confirmación (ej. 1 clic = marcar presente y avanzar), pero **no
reemplaza una UX real** (el reloj no puede mostrar nombres ni P/A/E de
forma dinámica). Queda anotado como posible extensión futura, no como
parte del plan inicial.

Artifact con el diagrama de arquitectura completo (dos caminos desde el
mismo teléfono, con la asimetría bidireccional vs. unidireccional bien
marcada):
**https://claude.ai/code/artifact/76227457-72d1-49cc-a953-ebbd04bd4681**

## 3. Decisión de alcance para el desarrollo

- **Móvil (Android, Kotlin)**: fuente de verdad. Funciona 100% offline
  y sincroniza con Tecnoauladom cuando hay señal.
- **Wear OS**: mini-app espejo, pasa lista de forma independiente sin
  sacar el teléfono.
- **TB39 / BLE genérico**: fuera del flujo de marcado; en una fase
  posterior se le puede sumar como avisador pasivo reusando
  `tb39_client.py` / el SDK `com.uwatch.sdk` ya documentado en este
  proyecto.

## 4. UX — wireframes de las 7 pantallas

Canvas de diseño publicado (editable), organizado en dos filas
rotuladas "MÓVIL" y "WEAR OS":
**https://claude.ai/code/artifact/6b60d77c-e658-46c3-ab60-fe58c896f42f**

**Set Móvil** (teléfono, orden del flujo):
1. Lista de Cursos — banner de estado de conexión, cursos con pill de
   sincronización (Sincronizado / Pendiente / Sin conexión), botón
   "Sincronizar Cursos".
2. Tarjeta de Alumno (modo flashcard) — nombre grande, progreso "3/25",
   tres botones grandes PRESENTE/AUSENTE/EXCUSA (verde/rojo/ámbar),
   avanza automático al tocar.
3. Resumen del Curso — conteo P/A/E, detalle por alumno, indicador de
   "guardado localmente" vs. sincronizado, botón "Guardar y Enviar".
4. Cola de Sincronización — registros pendientes de subir (curso,
   fecha, hora), botón "Reintentar" por ítem y "Reintentar todo ahora".

**Set Wear OS** (reloj circular, pantalla oscura):
1. Selector de Curso — lista corta, texto grande.
2. Tarjeta de Alumno — nombre + 3 botones P/A/E, mismo código de color.
3. Resumen mini — conteo compacto P/A/E + botón Enviar + ícono de
   estado offline.

Semántica de color ya fijada en todo el sistema:
**Presente = verde · Ausente = rojo · Excusa/Tardanza = ámbar.**

## 5. Especificación técnica heredada del documento original (sigue vigente)

- **API**: `GET /api/v1/profesor/cursos` (trae cursos + estudiantes),
  `POST /api/v1/asistencia/sincronizar` (sube el registro, con
  `registro_id_uuid`, `curso_id`, `fecha`, `hora_captura`, y array de
  `{estudiante_id, estado}` donde estado ∈ `P`/`A`/`E`).
- **DB local (Room)**: tablas `cursos`, `estudiantes`,
  `asistencia_registros` (con `sincronizado` 0/1),
  `asistencia_detalles`.
- **Sync**: offline-first, WorkManager reintenta cuando vuelve la red
  (`NetworkType.CONNECTED`).
- **Stack**: Kotlin, Compose for Wear OS, Room, Retrofit + OkHttp,
  WorkManager + Coroutines.
- **Fases sugeridas originalmente**: 1) DB y configuración, 2) UI
  Wear, 3) Red y sincronización, 4) QA y despliegue — 8 semanas total.
  A revisar/ajustar mañana ahora que el plan cubre también el móvil
  como pieza central (el documento original asumía que la app vivía
  solo en el reloj).

## 6. Para retomar mañana

1. Revisar y ajustar el plan de fases del punto 5 para reflejar que el
   móvil es la app principal (no el reloj).
2. Confirmar con qué reloj Wear OS se va a probar (emulador vs.
   dispositivo real).
3. Empezar por Fase 1: proyecto Android (app de teléfono primero,
   dado que es la fuente de verdad), entidades Room, DAOs.
4. Recién en una fase posterior: proyecto Wear OS espejo, y —opcional—
   integración de aviso pasivo al TB39 reusando el protocolo ya
   documentado en este mismo repo (`tb39_client.py`,
   `tb39_protocol_decoded.txt`, `resumen.md`).

## 7. Prototipo web — Multimedia, 22 estudiantes (2026-09-28)

Antes de arrancar el proyecto Android nativo se armó un prototipo que ya
se puede usar en clase, abriéndolo en el navegador del teléfono:
`pase-de-lista/index.html` (publicado también como artifact:
**https://claude.ai/artifact/Nhn4Gh1WtwbGHyVENAaVxu**).

Sigue los wireframes del punto 4 (set Móvil):
- **Tarjeta**: un estudiante a la vez con PRESENTE / AUSENTE / EXCUSA
  (verde / rojo / ámbar); avanza solo al siguiente sin marcar. En
  computadora funcionan las teclas P, A, E y ← →.
- **Lista**: los 22 a la vez, con "marcar sin marcar como presentes".
- **Resumen**: conteo P/A/E del día, quiénes faltaron, historial por
  fecha y exportación a CSV.
- **Alumnos**: se pega la lista real (un nombre por línea); al reordenar
  se conservan las asistencias ya guardadas. Muestra quién acumula más
  faltas.
- Barra superior de 22 celdas: una por estudiante, coloreada según su
  marca del día.

Datos: se guardan en la nube del artifact (colecciones `curso/multimedia`
y `asis/<fecha>`) y siempre también en el teléfono (`localStorage`), así
que funciona sin señal.

Enlace con el TB39: el resumen genera un aviso de texto de máximo 200
bytes (el límite de `MESSAGE_PUSH`). Todavía no se envía solo al reloj
porque falta decodificar el formato de `MessageData`; mientras, se puede
reenviar por WhatsApp Business y llega con la app parcheada
(`resumen.md`).

Pendiente: sincronizar con Tecnoauladom (punto 5) y pasar a la app
Android/Wear OS nativa.
