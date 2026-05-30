#!/usr/bin/env python3
"""Probe a DX-LR02 dongle for its configured baud rate and settings.

The M0/M1 mode pins on these dongles are NOT wired to CH340 DTR/RTS, so we
can't force the module into config mode from software. This script assumes
the module is in whatever mode its PCB hard-wires, and sends every common
config-query the module might recognise, at every supported UART baud rate,
then looks for a reply that makes sense.

If the module is hard-wired into transparent mode, none of these will reply —
the commands are simply aired over LoRa instead of being interpreted. In
that case no baud will ever produce a clean reply, which is itself useful
diagnostic information.

Run against each device:
    python3 read_config.py /dev/ttyUSB0
    python3 read_config.py /dev/ttyUSB1
"""

import sys
import time

import serial

BAUDS = [9600, 115200, 57600, 38400, 19200, 4800, 2400]

BINARY_PROBES = [
    (b"\xC1\xC1\xC1", "ebyte read-all-params (C1 C1 C1)"),
    (b"\xC3\xC3\xC3", "ebyte read-version (C3 C3 C3)"),
    (b"\xC1\x00\x06", "ebyte-v2 read-params (C1 00 06)"),
    (b"\xC1\x80\x06", "ebyte-v2 read-temp-params (C1 80 06)"),
]

ASCII_PROBES = [
    (b"+++", "Hayes escape +++"),
    (b"AT\r\n", "AT"),
    (b"AT\r", "AT (CR)"),
    (b"AT+VER\r\n", "AT+VER"),
    (b"AT+VERSION?\r\n", "AT+VERSION?"),
    (b"AT+BAUD?\r\n", "AT+BAUD?"),
    (b"AT+BPS?\r\n", "AT+BPS?"),
    (b"AT+ADDR?\r\n", "AT+ADDR?"),
    (b"AT+FRE?\r\n", "AT+FRE?"),
    (b"AT+CH?\r\n", "AT+CH?"),
    (b"AT+RX\r\n", "AT+RX"),
    (b"AT?\r\n", "AT?"),
    (b"AT+HELP\r\n", "AT+HELP"),
]


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    return sum(1 for c in data if 32 <= c < 127 or c in (10, 13, 9)) / len(data)


def try_probe(port: str, baud: int, probe: bytes) -> bytes:
    s = serial.Serial(port, baud, timeout=0.2)
    try:
        time.sleep(0.1)
        s.reset_input_buffer()
        if probe == b"+++":
            time.sleep(1.0)  # Hayes requires silence gap before the escape
            s.write(probe)
            s.flush()
            time.sleep(1.2)
        else:
            s.write(probe)
            s.flush()
        deadline = time.time() + 0.9
        buf = bytearray()
        while time.time() < deadline:
            chunk = s.read(256)
            if chunk:
                buf.extend(chunk)
                deadline = time.time() + 0.3
        return bytes(buf)
    finally:
        s.close()


def decode_ebyte_c1(resp: bytes) -> str | None:
    """Decode an Ebyte-style 6-byte config reply: C1 ADDH ADDL SPED CHAN OPTN."""
    for i in range(len(resp) - 5):
        if resp[i] == 0xC1:
            b = resp[i : i + 6]
            addh, addl, sped, chan, optn = b[1], b[2], b[3], b[4], b[5]
            parity_bits = (sped >> 6) & 0b11
            baud_bits = (sped >> 3) & 0b111
            air_bits = sped & 0b111
            baud_map = {
                0: 1200, 1: 2400, 2: 4800, 3: 9600,
                4: 19200, 5: 38400, 6: 57600, 7: 115200,
            }
            air_map = {
                0: "0.3k", 1: "1.2k", 2: "2.4k", 3: "4.8k",
                4: "9.6k", 5: "19.2k", 6: "19.2k", 7: "19.2k",
            }
            parity_map = {0: "8N1", 1: "8O1", 2: "8E1", 3: "8N1"}
            return (
                f"addr=0x{addh:02X}{addl:02X}  "
                f"uart_baud={baud_map.get(baud_bits, '?')}  "
                f"parity={parity_map.get(parity_bits, '?')}  "
                f"air_rate={air_map.get(air_bits, '?')}  "
                f"channel=0x{chan:02X}  options=0x{optn:02X}"
            )
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    port = sys.argv[1]
    print(f"probing {port}\n")

    found = []
    for baud in BAUDS:
        for probe, label in BINARY_PROBES + ASCII_PROBES:
            try:
                resp = try_probe(port, baud, probe)
            except Exception as e:
                print(f"  err baud={baud} {label}: {e}")
                continue
            if not resp:
                continue
            r = printable_ratio(resp)
            decoded = decode_ebyte_c1(resp)
            header = f"baud={baud:>6}  probe={label}"
            if decoded:
                print(f"★ {header}\n    {decoded}\n    raw={resp!r}\n")
                found.append(("decoded", baud, label, resp, decoded))
            elif r >= 0.7 and len(resp) >= 3:
                print(f"✓ {header}\n    ascii: {resp!r}\n")
                found.append(("ascii", baud, label, resp, None))
            elif len(resp) >= 4:
                print(f"· {header}  raw({len(resp)})={resp!r}")

    print("\n--- summary ---")
    if not found:
        print("no interpretable reply at any baud.")
        print("most likely cause: module is hard-wired in transparent mode,")
        print("so these commands are being transmitted over LoRa instead of")
        print("interpreted locally. You will need the vendor config tool on")
        print("Windows, or to bridge M0/M1 to 3V3 to enter config mode.")
        return 1
    for kind, baud, label, resp, decoded in found:
        print(f"[{kind}] baud={baud} probe={label}")
        if decoded:
            print(f"    {decoded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
