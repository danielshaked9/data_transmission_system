#!/usr/bin/env python3
"""Cross-baud sweep: try every (TX_baud, RX_baud) pair.

If the two DX-LR02 modules happen to be configured with different UART rates,
a single-baud sweep will never succeed. This tests both directions for each
ordered pair and reports anything with a clean pattern match or a high
printable-byte ratio.
"""

import itertools
import string
import sys
import time

import serial

PORT_A = "/dev/ttyUSB0"
PORT_B = "/dev/ttyUSB1"
BAUDS = [9600, 19200, 38400, 57600, 115200, 4800, 2400, 1200]
PATTERN = b"<<<" + (string.ascii_uppercase + string.digits).encode() + b">>>\n"
WAIT = 2.0


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    return sum(1 for c in data if 32 <= c < 127 or c in (10, 13)) / len(data)


def one_shot(tx_port: str, tx_baud: int, rx_port: str, rx_baud: int) -> bytes:
    tx = serial.Serial(tx_port, tx_baud, timeout=0.1)
    rx = serial.Serial(rx_port, rx_baud, timeout=0.1)
    try:
        time.sleep(0.15)
        tx.reset_input_buffer()
        rx.reset_input_buffer()
        tx.write(PATTERN)
        tx.flush()
        deadline = time.time() + WAIT
        buf = bytearray()
        while time.time() < deadline:
            chunk = rx.read(256)
            if chunk:
                buf.extend(chunk)
                deadline = time.time() + 0.3
        return bytes(buf)
    finally:
        tx.close()
        rx.close()


def main() -> int:
    print(f"cross-baud sweep  A={PORT_A}  B={PORT_B}")
    print(f"pattern ({len(PATTERN)} B): {PATTERN!r}\n")

    results = []
    pairs = list(itertools.product(BAUDS, BAUDS))
    total = len(pairs) * 2
    i = 0
    for tx_baud, rx_baud in pairs:
        for direction, tx_port, rx_port in (
            ("A→B", PORT_A, PORT_B),
            ("B→A", PORT_B, PORT_A),
        ):
            i += 1
            try:
                got = one_shot(tx_port, tx_baud, rx_port, rx_baud)
            except Exception as e:
                print(f"[{i:>3}/{total}] {direction} tx={tx_baud:>6} rx={rx_baud:>6}  ERR {e}")
                continue
            matched = PATTERN.strip() in got
            r = printable_ratio(got)
            flag = "★MATCH" if matched else ("  " if r < 0.7 else "high")
            print(
                f"[{i:>3}/{total}] {direction} tx={tx_baud:>6} rx={rx_baud:>6} "
                f"{flag}  len={len(got):>3}  printable={r:.0%}  {got[:60]!r}"
            )
            results.append((matched, r, direction, tx_baud, rx_baud, got))

    print("\n--- summary ---")
    matches = [r for r in results if r[0]]
    if matches:
        print("clean matches:")
        for m in matches:
            _, _, d, tx, rx, _ = m
            print(f"  {d}  tx={tx}  rx={rx}")
        return 0

    results.sort(key=lambda r: r[1], reverse=True)
    print("no clean match. top 5 by printable ratio:")
    for _, r, d, tx, rx, got in results[:5]:
        print(f"  {d} tx={tx} rx={rx} printable={r:.0%} got={got[:60]!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
