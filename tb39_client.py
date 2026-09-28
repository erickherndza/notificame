#!/usr/bin/env python3
"""
tb39_client.py - Cliente BLE en Python para el TB39, basado en el protocolo
real extraído del SDK com.uwatch.sdk (decompilado de la app
com.sinophy.smartbracelet con jadx).

Reimplementa en Python:
  - UWatchCommandConst.generateCommand()  -> generate_command()
  - UWatchResponse.Companion.generateResponse() -> parse_response()
  - Los decoders más útiles de UWatchDispatch.dispatchResponseInMain()

UUIDs (UWatchServiceUUIDConst):
  SERVICE_UUID               = 0000FF12-...
  WRITE_CHARACTERISTIC_UUID  = 0000FF13-...  (write-without-response)
  NOTIFY_CHARACTERISTIC_UUID = 0000FF14-...  (notify)

Uso:
  python tb39_client.py --address <DIRECCION> --query all
  python tb39_client.py --address <DIRECCION> --query battery
  python tb39_client.py --address <DIRECCION> --sync-time
  python tb39_client.py --address <DIRECCION> --find start|stop
  python tb39_client.py --address <DIRECCION> --raw 0x51 0x00        # comando crudo
"""

import argparse
import asyncio
import time
from datetime import datetime

from bleak import BleakClient

SERVICE_UUID = "0000ff12-0000-1000-8000-00805f9b34fb"
WRITE_CHARACTERISTIC_UUID = "0000ff13-0000-1000-8000-00805f9b34fb"
NOTIFY_CHARACTERISTIC_UUID = "0000ff14-0000-1000-8000-00805f9b34fb"

# ---------------------------------------------------------------------------
# Catálogo de comandos (com.uwatch.sdk.UWatchCommandConst.Command), valores
# ya convertidos a unsigned (0-255) para trabajar cómodo en Python.
# ---------------------------------------------------------------------------
COMMANDS = {
    128: "DEVICE_SWITCH_SETTING",
    129: "DEVICE_BIND",
    130: "DEVICE_BIND_FINISH",
    131: "ALARM",
    133: "INTERVAL_REMIND",
    134: "SOCIAL_SWITCH_SETTING",
    144: "MUSIC_CONTROL",
    145: "REMOTE_PHOTO",
    160: "MESSAGE_PUSH",
    161: "WEATHER_PUSH",
    164: "CONTACT_SETTING",
    165: "INCOMING_CALL",
    166: "INCOMING_MUTE",
    176: "TARGET_SETTING",
    179: "SPORTS_DATA",
    181: "SLEEP_DATA",
    182: "AUTO_SLEEP_MONITOR_TIME",
    184: "HEART_RATE_DATA_DELETE",
    185: "HEART_RATE_DATA",
    186: "AUTO_HEART_RATE_MONITOR_INTERVAL",
    187: "HEART_RATE_ALARM_RANGE",
    188: "LONG_SIT_REMINDER",
    189: "HRV_DATA",
    190: "STATIC_CALORIE_SWITCH",
    191: "QUICKLY_HEART_RATE_DATA",
    192: "TIMED_SPORTS_DATA_TOTAL_COUNT",
    193: "TIMED_SPORTS_DATA",
    194: "TIMED_SPORTS_DATA_DELETE",
    196: "REALTIME_MEASURE_REPORT_SWITCH",
    197: "REALTIME_MEASURE_DATA",
    198: "AUTO_MEASURE_INTERVAL",
    199: "STEP_COUNT_TOADY_DATA",
    200: "STEP_COUNT_HISTORY_DATA",
    201: "SLEEP_HISTORY_DATA",
    202: "LATEST_MEASURE_DATA",
    224: "DIAL_PUSH",
    225: "CUSTOM_DIAL_PUSH_SETTING",
    227: "QRCODE_SETTING",
    80: "SYNC_TIME",
    81: "GET_BATTERY",
    82: "SCREEN_BRIGHTNESS",
    83: "LANGUAGE",
    84: "DEVICE_UNIT",
    85: "RESTORE_FACTORY_SETTINGS",
    86: "SCREEN_TIME",
    87: "DO_NOT_DISTURB",
    88: "FIND_DEVICE",
    89: "FIND_PHONE",
    90: "WEATHER_UNIT",
    91: "TIME_UNIT",
    92: "DEVICE_INFO",
    93: "PHONE_TYPE",
    112: "PERSONAL_INFO",
}


def cmd_name(cmd: int) -> str:
    return COMMANDS.get(cmd, f"UNKNOWN_0x{cmd:02X}")


# ---------------------------------------------------------------------------
# Frame builder (== UWatchCommandConst.generateCommand)
# ---------------------------------------------------------------------------
def generate_command(cmd: int, b3: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    frame = bytearray(6 + length)
    frame[0] = 0x00
    frame[1] = cmd & 0xFF
    frame[2] = 0x01  # CommandType.REQUEST
    frame[3] = 0x00
    frame[4] = (length + 1) & 0xFF
    frame[5] = b3 & 0xFF
    frame[6:6 + length] = payload
    return bytes(frame)


# ---------------------------------------------------------------------------
# Frame parser (== UWatchResponse.Companion.generateResponse)
# ---------------------------------------------------------------------------
def parse_response(raw: bytes):
    if len(raw) < 3:
        return None
    command_type = raw[2]
    if command_type not in (1, 2, 3):
        return None

    is_response = command_type == 2
    is_notify = command_type == 3
    if not is_response and not is_notify:
        return None
    if is_response and len(raw) < 7:
        return None
    if is_notify and len(raw) < 6:
        return None

    cmd = raw[1]
    frame_len = raw[4]

    if is_response:
        data_len = frame_len - 1
        data_start = 6
    elif cmd == 0xC7:  # STEP_COUNT_TOADY_DATA es un caso especial (igual que response)
        data_len = frame_len - 1
        data_start = 6
    else:
        data_len = frame_len
        data_start = 5

    data = bytes(raw[data_start:data_start + data_len])
    return {
        "seq": raw[0],
        "cmd": cmd,
        "cmd_name": cmd_name(cmd),
        "is_response": is_response,
        "is_notify": is_notify,
        "action_cmd": raw[5],
        "data": data,
    }


# ---------------------------------------------------------------------------
# Decoders de respuestas conocidas (== UWatchDispatch.dispatchResponseInMain)
# ---------------------------------------------------------------------------
def decode_response(parsed: dict):
    cmd = parsed["cmd"]
    d = parsed["data"]

    try:
        if cmd == 81 and len(d) >= 1:  # GET_BATTERY
            level = d[0] & 0x7F
            charging = bool((d[0] >> 7) & 1)
            return f"batería: {level}% {'(cargando)' if charging else ''}"

        if cmd == 83 and len(d) >= 1:  # LANGUAGE
            langs = {0: "English", 1: "Simplified Chinese", 3: "Spanish"}
            return f"idioma: {langs.get(d[0], f'código {d[0]}')}"

        if cmd == 84 and len(d) >= 1:  # DEVICE_UNIT
            return f"unidad: {'métrico' if d[0] == 0 else 'imperial'}"

        if cmd == 91 and len(d) >= 1:  # TIME_UNIT
            return f"formato hora: {'12h' if d[0] == 0 else '24h'}"

        if cmd == 112 and len(d) >= 4:  # PERSONAL_INFO
            sex = "hombre" if d[0] == 0 else "mujer"
            return f"perfil: {sex}, {d[1]} años, {d[2]}cm, {d[3]}kg"

        if cmd == 128 and len(d) >= 2:  # DEVICE_SWITCH_SETTING (== DeviceSwitchData)
            b4, b5 = d[0], d[1]
            flags = {
                "antiLostSwitch (antipérdida)": bool(b4 & 1),
                "raiseHandBrightenScreenSwitch (subir muñeca enciende pantalla)": bool((b4 >> 1) & 1),
                "autoSyncSwitch (sincronización automática)": bool((b4 >> 2) & 1),
                "sleepMonitorSwitch (monitoreo de sueño)": bool((b4 >> 4) & 1),
                "messageReminderSwitch (aviso de mensajes)": bool((b4 >> 5) & 1),
                "regularSportsDataUploadSwitch (subida periódica de datos deportivos)": bool((b4 >> 6) & 1),
                "goalAchievementSwitch (logro de meta)": bool((b4 >> 7) & 1),
                "messageReminderScreenDisplaySwitch (mostrar mensaje en pantalla)": bool((b5 >> 1) & 1),
                "soundSwitch (sonido)": bool((b5 >> 2) & 1),
                "vibrationSwitch (vibración)": bool((b5 >> 3) & 1),
                "regularHealthDataUploadSwitch (subida periódica de datos de salud)": bool((b5 >> 4) & 1),
                "messageReminderVibrationSwitch (vibrar con mensajes)": bool((b5 >> 5) & 1),
            }
            lines = [f"    {'ON ' if v else 'off'} - {k}" for k, v in flags.items()]
            return "switches:\n" + "\n".join(lines)

        if cmd == 87 and len(d) >= 5:  # DO_NOT_DISTURB
            on = d[0] == 1
            return (f"no molestar: {'ON' if on else 'off'} "
                    f"({d[1]:02d}:{d[2]:02d} - {d[3]:02d}:{d[4]:02d})")

        if cmd == 199 and len(d) >= 5:  # STEP_COUNT_TOADY_DATA
            if d[0] == 0:
                steps = d[1] | (d[2] << 8) | (d[3] << 16) | (d[4] << 24)
                return f"pasos de hoy: {steps}"

        if cmd == 181 and len(d) >= 6:  # SLEEP_DATA
            deep_min = d[0] | (d[1] << 8)
            light_min = d[2] | (d[3] << 8)
            total_min = d[4] | (d[5] << 8)
            return f"sueño: total={total_min}min profundo={deep_min}min ligero={light_min}min"

        if cmd == 202:  # LATEST_MEASURE_DATA
            action = parsed["action_cmd"]
            if action == 0 and len(d) >= 5:
                hr = d[4]
                return f"última FC: {hr} bpm"
            if action == 1 and len(d) >= 5:
                spo2 = d[4]
                return f"último SpO2: {spo2}%"
    except IndexError:
        pass

    return f"raw data: {d.hex(' ')}"


# ---------------------------------------------------------------------------
# Comandos de alto nivel listos para usar
# ---------------------------------------------------------------------------
def cmd_get_battery():
    return generate_command(81, 0)


def cmd_get_personal_info():
    return generate_command(112, 0)


def cmd_get_device_unit():
    return generate_command(84, 0)


def cmd_get_time_unit():
    return generate_command(91, 0)


def cmd_get_language():
    return generate_command(83, 0)


def cmd_get_steps_today():
    return generate_command(199, 0, bytes([0]))


def cmd_get_sleep():
    return generate_command(181, 0)


def cmd_get_device_switch():
    return generate_command(128, 0)


def cmd_get_do_not_disturb():
    return generate_command(87, 0)


def cmd_get_latest_heart_rate():
    return generate_command(202, 0)  # MeasureType.HEART_RATE


def cmd_get_latest_spo2():
    return generate_command(202, 1)  # MeasureType.BLOOD_OXYGEN


def cmd_sync_time():
    epoch = int(time.time())
    payload = bytes([
        12,
        epoch & 0xFF,
        (epoch >> 8) & 0xFF,
        (epoch >> 16) & 0xFF,
        (epoch >> 24) & 0xFF,
    ])
    return generate_command(80, 1, payload)


def cmd_find_device(start: bool):
    return generate_command(88, 0 if start else 1)


QUERY_MAP = {
    "battery": cmd_get_battery,
    "personal_info": cmd_get_personal_info,
    "device_unit": cmd_get_device_unit,
    "time_unit": cmd_get_time_unit,
    "language": cmd_get_language,
    "steps_today": cmd_get_steps_today,
    "sleep": cmd_get_sleep,
    "device_switch": cmd_get_device_switch,
    "do_not_disturb": cmd_get_do_not_disturb,
    "heart_rate": cmd_get_latest_heart_rate,
    "spo2": cmd_get_latest_spo2,
}


# ---------------------------------------------------------------------------
# Cliente BLE
# ---------------------------------------------------------------------------
async def run(address: str, requests: list, timeout: float):
    def log(msg):
        print(f"[{datetime.now().isoformat(timespec='milliseconds')}] {msg}")

    log(f"Conectando a {address}...")
    async with BleakClient(address) as client:
        log(f"Conectado: {client.is_connected}")

        pending_responses = []

        def handler(_sender, data: bytearray):
            raw = bytes(data)
            parsed = parse_response(raw)
            if parsed is None:
                log(f"NOTIFY (sin parsear): {raw.hex(' ')}")
                return
            kind = "NOTIFY" if parsed["is_notify"] else "RESPONSE"
            decoded = decode_response(parsed)
            log(f"{kind} cmd={parsed['cmd_name']} (0x{parsed['cmd']:02X}) -> {decoded}")
            pending_responses.append(parsed)

        await client.start_notify(NOTIFY_CHARACTERISTIC_UUID, handler)

        for name, frame in requests:
            log(f"-> Enviando {name}: {frame.hex(' ')}")
            await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, frame, response=False)
            await asyncio.sleep(1.5)

        log(f"Esperando respuestas adicionales ({timeout:.0f}s)...")
        await asyncio.sleep(timeout)

        await client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
        log("Desconectando.")


def main():
    parser = argparse.ArgumentParser(description="Cliente BLE para el TB39 (protocolo com.uwatch.sdk)")
    parser.add_argument("--address", required=True, help="dirección/UUID del reloj")
    parser.add_argument("--query", choices=list(QUERY_MAP.keys()) + ["all"], help="consulta a enviar")
    parser.add_argument("--sync-time", action="store_true", help="sincronizar la hora del reloj con la del sistema")
    parser.add_argument("--find", choices=["start", "stop"], help="activar/detener 'buscar reloj' (vibración)")
    parser.add_argument("--raw", nargs="+", metavar="BYTE", help="comando crudo: CMD B3 [PAYLOAD_BYTES...] en hex, ej: 0x51 0x00")
    parser.add_argument("--wait", type=float, default=5.0, help="segundos extra esperando respuestas al final")
    args = parser.parse_args()

    requests = []

    if args.query == "all":
        for name, fn in QUERY_MAP.items():
            requests.append((name, fn()))
    elif args.query:
        requests.append((args.query, QUERY_MAP[args.query]()))

    if args.sync_time:
        requests.append(("sync_time", cmd_sync_time()))

    if args.find:
        requests.append((f"find_{args.find}", cmd_find_device(args.find == "start")))

    if args.raw:
        values = [int(x, 0) for x in args.raw]
        cmd, b3, payload = values[0], values[1], bytes(values[2:])
        requests.append((f"raw_0x{cmd:02X}", generate_command(cmd, b3, payload)))

    if not requests:
        print("No especificaste ninguna acción. Usa --query, --sync-time, --find o --raw.")
        return

    asyncio.run(run(args.address, requests, args.wait))


if __name__ == "__main__":
    main()
