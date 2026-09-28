#!/usr/bin/env python3
"""
scan_watch.py - Escanea dispositivos BLE cercanos y, opcionalmente, se conecta
a uno de ellos para mapear todos sus servicios y characteristics GATT.

Uso:
    # 1) Solo escanear (por defecto 8 segundos)
    python scan_watch.py

    # 2) Escanear y luego conectar a un dispositivo por dirección (MAC / UUID en macOS)
    python scan_watch.py --connect AA:BB:CC:DD:EE:FF

    # 3) Escanear y conectar a un dispositivo por nombre (coincidencia parcial, case-insensitive)
    python scan_watch.py --connect-name TB39

Opciones útiles:
    --scan-time N     segundos de escaneo (default: 8)
    --out FILE        archivo de salida del mapa GATT (default: tb39_gatt_map.txt)
"""

import argparse
import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner


async def scan(scan_time: float):
    print(f"Escaneando BLE durante {scan_time:.0f} segundos...\n")
    devices = await BleakScanner.discover(timeout=scan_time, return_adv=True)

    if not devices:
        print("No se encontraron dispositivos BLE.")
        return {}

    # devices: dict[address] -> (BLEDevice, AdvertisementData)
    rows = []
    for address, (dev, adv) in devices.items():
        name = dev.name or adv.local_name or "(sin nombre)"
        rssi = adv.rssi if adv.rssi is not None else "?"
        rows.append((name, address, rssi))

    rows.sort(key=lambda r: (r[2] if isinstance(r[2], int) else -999), reverse=True)

    print(f"{'Nombre':30} {'Dirección':20} {'RSSI'}")
    print("-" * 60)
    for name, address, rssi in rows:
        print(f"{name:30} {address:20} {rssi}")
    print()

    return devices


def props_to_str(props):
    return ", ".join(sorted(props))


async def map_gatt(address: str, out_path: str):
    print(f"\nConectando a {address}...")
    async with BleakClient(address) as client:
        connected = client.is_connected
        print(f"Conectado: {connected}")
        if not connected:
            print("No se pudo conectar al dispositivo.")
            return

        lines = []
        lines.append(f"Mapa GATT - dispositivo {address}")
        lines.append(f"Generado: {datetime.now().isoformat()}")
        lines.append("=" * 70)

        services = client.services
        for service in services:
            lines.append("")
            lines.append(f"[Service] {service.uuid}")
            if service.description:
                lines.append(f"    Descripción: {service.description}")

            for char in service.characteristics:
                props = props_to_str(char.properties)
                lines.append(f"  [Characteristic] {char.uuid}")
                lines.append(f"      Handle: {char.handle}")
                lines.append(f"      Propiedades: {props}")
                if char.description:
                    lines.append(f"      Descripción: {char.description}")

                for descriptor in char.descriptors:
                    lines.append(
                        f"      [Descriptor] {descriptor.uuid} (handle: {descriptor.handle})"
                    )

        text = "\n".join(lines) + "\n"

        with open(out_path, "w") as f:
            f.write(text)

        print(f"\nMapa GATT guardado en: {out_path}")
        print(text)


async def main():
    parser = argparse.ArgumentParser(description="Escanea y mapea dispositivos BLE")
    parser.add_argument("--scan-time", type=float, default=8.0, help="segundos de escaneo")
    parser.add_argument("--connect", type=str, default=None, help="dirección/UUID exacta a la que conectar")
    parser.add_argument("--connect-name", type=str, default=None, help="nombre (parcial) a buscar y conectar")
    parser.add_argument("--out", type=str, default="tb39_gatt_map.txt", help="archivo de salida del mapa GATT")
    parser.add_argument("--no-scan", action="store_true", help="omitir el escaneo y conectar directo (requiere --connect)")
    args = parser.parse_args()

    target_address = args.connect

    if not args.no_scan:
        devices = await scan(args.scan_time)

        if args.connect_name and not target_address:
            match = None
            for address, (dev, adv) in devices.items():
                name = dev.name or adv.local_name or ""
                if args.connect_name.lower() in name.lower():
                    match = address
                    break
            if match:
                print(f"Coincidencia por nombre '{args.connect_name}' -> {match}")
                target_address = match
            else:
                print(f"No se encontró ningún dispositivo con nombre que contenga '{args.connect_name}'.")

    if target_address:
        await map_gatt(target_address, args.out)
    else:
        print("\nNo se especificó dispositivo a conectar (usa --connect o --connect-name).")
        print("Revisa la lista de arriba y vuelve a correr:")
        print(f"  python {sys.argv[0]} --no-scan --connect <DIRECCION>")


if __name__ == "__main__":
    asyncio.run(main())
