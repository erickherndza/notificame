#!/usr/bin/env python3
"""
parse_btsnoop.py - Parser mínimo del formato btsnoop (H4) para extraer
tráfico ATT (GATT) relevante: Write Command/Request, Notify, Indicate,
Read Response. Además mapea connection handle -> dirección BLE del peer
usando los eventos LE Connection Complete / Enhanced Connection Complete,
para poder identificar cuál conexión corresponde al reloj.

No depende de tshark/Wireshark.

Uso:
    python parse_btsnoop.py tb39_btsnoop_hci.log
"""

import struct
import sys

ATT_OPCODE_NAMES = {
    0x01: "Error Response",
    0x02: "Exchange MTU Request",
    0x03: "Exchange MTU Response",
    0x08: "Read By Type Request",
    0x09: "Read By Type Response",
    0x0A: "Read Request",
    0x0B: "Read Response",
    0x10: "Read By Group Type Request",
    0x11: "Read By Group Type Response",
    0x12: "Write Request",
    0x13: "Write Response",
    0x16: "Prepare Write Request",
    0x17: "Prepare Write Response",
    0x18: "Execute Write Request",
    0x19: "Execute Write Response",
    0x1B: "Handle Value Notification",
    0x1D: "Handle Value Indication",
    0x1E: "Handle Value Confirmation",
    0x52: "Write Command",
}

INTERESTING_OPCODES = {0x0B, 0x12, 0x1B, 0x1D, 0x52}


def parse_btsnoop(path):
    with open(path, "rb") as f:
        data = f.read()

    magic = data[0:8]
    if magic != b"btsnoop\x00":
        raise ValueError("No es un archivo btsnoop válido")

    version, datalink = struct.unpack(">II", data[8:16])
    offset = 16

    records = []
    handle_to_addr = {}
    att_events = []

    while offset < len(data):
        if offset + 24 > len(data):
            break
        orig_len, incl_len, flags, drops, ts = struct.unpack(
            ">IIIIq", data[offset:offset + 24]
        )
        offset += 24
        pkt = data[offset:offset + incl_len]
        offset += incl_len

        if not pkt:
            continue

        h4_type = pkt[0]
        direction = "RX" if (flags & 0x1) else "TX"

        if h4_type == 0x04:  # HCI Event
            parse_hci_event(pkt[1:], handle_to_addr)
        elif h4_type == 0x02:  # ACL Data
            parse_acl(pkt[1:], direction, ts, att_events, handle_to_addr)

    return handle_to_addr, att_events


def parse_hci_event(evt, handle_to_addr):
    if len(evt) < 2:
        return
    code = evt[0]
    plen = evt[1]
    params = evt[2:2 + plen]

    if code == 0x3E and len(params) >= 1:  # LE Meta Event
        subevent = params[0]
        if subevent == 0x01 and len(params) >= 19:
            # LE Connection Complete
            handle = struct.unpack("<H", params[3:5])[0] & 0x0FFF
            addr_type = params[5]
            addr = params[6:12]
            addr_str = ":".join(f"{b:02X}" for b in reversed(addr))
            handle_to_addr[handle] = (addr_str, "public" if addr_type == 0 else "random")
        elif subevent == 0x0A and len(params) >= 30:
            # LE Enhanced Connection Complete
            handle = struct.unpack("<H", params[2:4])[0] & 0x0FFF
            addr_type = params[4]
            addr = params[5:11]
            addr_str = ":".join(f"{b:02X}" for b in reversed(addr))
            handle_to_addr[handle] = (addr_str, "public" if addr_type == 0 else "random")


def parse_acl(acl, direction, ts, att_events, handle_to_addr):
    if len(acl) < 4:
        return
    handle_flags = struct.unpack("<H", acl[0:2])[0]
    handle = handle_flags & 0x0FFF
    data_len = struct.unpack("<H", acl[2:4])[0]
    payload = acl[4:4 + data_len]

    if len(payload) < 4:
        return

    l2cap_len = struct.unpack("<H", payload[0:2])[0]
    cid = struct.unpack("<H", payload[2:4])[0]
    l2cap_payload = payload[4:4 + l2cap_len]

    if cid != 0x0004 or not l2cap_payload:  # 0x0004 = ATT protocol
        return

    opcode = l2cap_payload[0]
    if opcode not in INTERESTING_OPCODES:
        return

    att_events.append({
        "ts": ts,
        "direction": direction,
        "handle": handle,
        "opcode": opcode,
        "opcode_name": ATT_OPCODE_NAMES.get(opcode, f"0x{opcode:02X}"),
        "raw": l2cap_payload,
    })


def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <archivo btsnoop>")
        sys.exit(1)

    path = sys.argv[1]
    handle_to_addr, att_events = parse_btsnoop(path)

    print("=== Conexiones LE detectadas (connection handle -> dirección BLE) ===")
    if not handle_to_addr:
        print("(ninguna encontrada)")
    for handle, (addr, addr_type) in handle_to_addr.items():
        n_events = sum(1 for e in att_events if e["handle"] == handle)
        print(f"  handle=0x{handle:04X}  addr={addr} ({addr_type})  paquetes ATT relevantes={n_events}")

    print(f"\n=== Total de paquetes ATT relevantes: {len(att_events)} ===\n")

    for e in att_events:
        addr_info = handle_to_addr.get(e["handle"])
        addr_str = addr_info[0] if addr_info else "?"
        raw_hex = e["raw"].hex(" ")
        print(f"[{e['direction']}] handle=0x{e['handle']:04X} addr={addr_str} "
              f"opcode={e['opcode_name']} ({hex(e['opcode'])})  data: {raw_hex}")


if __name__ == "__main__":
    main()
