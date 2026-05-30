#!/usr/bin/env python3
"""Sweep DX-LR02 UART baud rates until messages sent on A arrive cleanly on B.

DX-LR02 supports 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200.
For each candidate we assume both modules share the same UART baud (default
factory behaviour) and send a long ASCII pattern that's trivial to recognize
against line noise.
"""

import string
import sys
import time

import serial

PORT_A = "/dev/ttyUSB0"
PORT_B = "/dev/ttyUSB1"
BAUDS = [9600, 115200, 57600, 38400, 19200, 4800, 2400, 1200]
PATTERN = b"===PROBE===" + string.ascii_uppercase.encode() * 2 + b"===END===\n"
WAIT_PER_TEST = 3.0


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    ok = sum(1 for c in data if 32 <= c < 127 or c in (10, 13))
    return ok / len(data)


def try_baud(baud: int) -> tuple[bool, bytes, bytes]:
    a = serial.Serial(PORT_A, baud, timeout=0.2)
    b = serial.Serial(PORT_B, baud, timeout=0.2)
    try:
        time.sleep(0.1)
        a.reset_input_buffer()
        b.reset_input_buffer()

        a.write(PATTERN)
        a.flush()

        deadline = time.time() + WAIT_PER_TEST
        got_b = bytearray()
        while time.time() < deadline:
            chunk = b.read(256)
            if chunk:
                got_b.extend(chunk)
                deadline = time.time() + 0.4

        b.write(PATTERN)
        b.flush()
        deadline = time.time() + WAIT_PER_TEST
        got_a = bytearray()
        while time.time() < deadline:
            chunk = a.read(256)
            if chunk:
                got_a.extend(chunk)
                deadline = time.time() + 0.4

        ok = PATTERN.strip() in bytes(got_b) and PATTERN.strip() in bytes(got_a)
        return ok, bytes(got_b), bytes(got_a)
    finally:
        a.close()
        b.close()


def main() -> int:
    print(f"sweeping bauds on {PORT_A} <-> {PORT_B}")
    print(f"pattern ({len(PATTERN)} bytes): {PATTERN!r}\n")
    best = None
    for baud in BAUDS:
        try:
            ok, rx_b, rx_a = try_baud(baud)
        except Exception as e:
            print(f"{baud:>6}: error {e}")
            continue

        r_b = printable_ratio(rx_b)
        r_a = printable_ratio(rx_a)
        tag = "MATCH" if ok else f"printable A→B={r_b:.0%} B→A={r_a:.0%}"
        print(f"{baud:>6}: {tag}")
        print(f"          A→B rx ({len(rx_b)}): {rx_b[:80]!r}")
        print(f"          B→A rx ({len(rx_a)}): {rx_a[:80]!r}")
        if ok:
            print(f"\n✔ confirmed working baud: {baud}")
            return 0
        score = r_a + r_b
        if best is None or score > best[0]:
            best = (score, baud)

    print("\n✘ no baud produced a clean round-trip.")
    if best:
        print(f"  best guess by printable ratio: {best[1]} (score {best[0]:.2f})")
    print("  likely causes: modules on different network IDs / channels,")
    print("  or UART baud outside the tested set (check module config tool).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
