#!/usr/bin/env python3
"""
sniff_watch.py - Se conecta a un dispositivo BLE, se suscribe a TODAS las
characteristics con notify/indicate, y registra en vivo (pasivamente) cada
paquete que el dispositivo envíe, con timestamp y en hex/ascii.

Esto sirve para capturar tráfico real del protocolo propietario (por ejemplo
al presionar un botón del reloj, recibir una notificación, moverte, etc.)
sin necesidad de conocer de antemano los comandos del fabricante.

Uso:
    python sniff_watch.py --address <DIRECCION> --duration 25 --out tb39_live_capture.log

Opcionalmente puede enviar un único byte "probe" no destructivo a una
characteristic de escritura (--probe-uuid / --probe-hex), útil solo si
sabes lo que estás probando.
"""

import argparse
import asyncio
from datetime import datetime

from bleak import BleakClient


def hexdump(data: bytes) -> str:
    h = data.hex(" ")
    ascii_repr = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{h}   |{ascii_repr}|"


async def main():
    parser = argparse.ArgumentParser(description="Captura pasiva de notificaciones BLE")
    parser.add_argument("--address", required=True, help="dirección/UUID del dispositivo")
    parser.add_argument("--duration", type=float, default=25.0, help="segundos de captura")
    parser.add_argument("--out", type=str, default="tb39_live_capture.log", help="archivo de log")
    parser.add_argument("--probe-uuid", type=str, default=None, help="UUID de characteristic donde escribir un probe")
    parser.add_argument("--probe-hex", type=str, default=None, help="bytes en hex a escribir, ej: '01'")
    args = parser.parse_args()

    log_lines = []

    def log(msg: str):
        line = f"[{datetime.now().isoformat(timespec='milliseconds')}] {msg}"
        print(line)
        log_lines.append(line)

    log(f"Conectando a {args.address}...")
    async with BleakClient(args.address) as client:
        log(f"Conectado: {client.is_connected}")

        notify_chars = []
        for service in client.services:
            for char in service.characteristics:
                if "notify" in char.properties or "indicate" in char.properties:
                    notify_chars.append(char)

        if not notify_chars:
            log("El dispositivo no expone ninguna characteristic notify/indicate.")
        else:
            log(f"Suscribiendo a {len(notify_chars)} characteristic(s) notify/indicate:")
            for c in notify_chars:
                log(f"  - {c.uuid} (service {c.service_uuid})")

            def make_handler(char_uuid):
                def handler(_sender, data: bytearray):
                    log(f"NOTIFY {char_uuid}: {hexdump(bytes(data))}")
                return handler

            for c in notify_chars:
                await client.start_notify(c.uuid, make_handler(c.uuid))

        if args.probe_uuid and args.probe_hex:
            payload = bytes.fromhex(args.probe_hex)
            log(f"Enviando probe a {args.probe_uuid}: {hexdump(payload)}")
            await client.write_gatt_char(args.probe_uuid, payload, response=False)

        log(f"Capturando durante {args.duration:.0f}s. Interactúa con el reloj ahora "
            f"(botón, gira la muñeca, recibe una notificación en el celular, etc.)...")
        await asyncio.sleep(args.duration)

        for c in notify_chars:
            try:
                await client.stop_notify(c.uuid)
            except Exception:
                pass

        log("Captura finalizada, desconectando.")

    with open(args.out, "w") as f:
        f.write("\n".join(log_lines) + "\n")

    print(f"\nLog guardado en: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
