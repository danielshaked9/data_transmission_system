#!/usr/bin/env python3
"""Send messages between two DX-LR02 LoRa modules over CH340 USB-serial adapters.

The DX-LR02 runs in transparent mode by default: bytes written to the serial
port are transmitted over LoRa, and bytes received over the air appear on the
serial port of the paired module. For the link to work both modules must share
frequency, air-speed, network ID and address settings (configured via the
vendor tool or AT commands).

Usage:
    python3 lora_chat.py test                 # A -> B then B -> A ping test
    python3 lora_chat.py chat                 # two-way interactive chat
    python3 lora_chat.py send "hello" --from A
    python3 lora_chat.py listen --on B
"""

import argparse
import queue
import sys
import threading
import time

import serial

PORT_A = "/dev/ttyUSB0"
PORT_B = "/dev/ttyUSB1"
BAUD = 9600
READ_TIMEOUT = 0.2


def open_port(path: str) -> serial.Serial:
    return serial.Serial(
        port=path,
        baudrate=BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=READ_TIMEOUT,
    )


def send(port: serial.Serial, text: str) -> None:
    payload = text.encode("utf-8") + b"\n"
    port.write(payload)
    port.flush()


def drain(port: serial.Serial, wait: float = 1.5) -> str:
    """Read whatever arrives within `wait` seconds."""
    deadline = time.time() + wait
    buf = bytearray()
    while time.time() < deadline:
        chunk = port.read(256)
        if chunk:
            buf.extend(chunk)
            deadline = time.time() + 0.3
    return buf.decode("utf-8", errors="replace")


def cmd_test(a: serial.Serial, b: serial.Serial) -> int:
    print(f"[test] A={a.port}  B={b.port}  baud={BAUD}")

    msg_ab = f"ping-A->B {time.time():.0f}"
    print(f"[A→B] sending: {msg_ab!r}")
    send(a, msg_ab)
    got_b = drain(b)
    print(f"[B rx] {got_b!r}")

    msg_ba = f"ping-B->A {time.time():.0f}"
    print(f"[B→A] sending: {msg_ba!r}")
    send(b, msg_ba)
    got_a = drain(a)
    print(f"[A rx] {got_a!r}")

    ok = msg_ab in got_b and msg_ba in got_a
    print("[test]", "PASS" if ok else "FAIL — check pairing (freq/netid/addr) and antennas")
    return 0 if ok else 1


def cmd_send(port: serial.Serial, text: str) -> int:
    send(port, text)
    print(f"sent {len(text)} bytes on {port.port}")
    return 0


def cmd_listen(port: serial.Serial) -> int:
    print(f"listening on {port.port}  (Ctrl-C to quit)")
    try:
        while True:
            chunk = port.read(256)
            if chunk:
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                sys.stdout.flush()
    except KeyboardInterrupt:
        print()
        return 0


def cmd_chat(a: serial.Serial, b: serial.Serial) -> int:
    """Type `A: hello` or `B: hello` to send from that side.

    Incoming messages from either module are printed as they arrive.
    """
    print("chat mode — prefix lines with 'A:' or 'B:'. Ctrl-D to quit.")
    stop = threading.Event()

    def reader(label: str, port: serial.Serial) -> None:
        while not stop.is_set():
            chunk = port.read(256)
            if chunk:
                text = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    print(f"\n[{label} rx] {text}\n> ", end="", flush=True)

    threads = [
        threading.Thread(target=reader, args=("A", a), daemon=True),
        threading.Thread(target=reader, args=("B", b), daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            line = input("> ")
            if not line:
                continue
            if line[:2].upper() == "A:":
                send(a, line[2:].strip())
            elif line[:2].upper() == "B:":
                send(b, line[2:].strip())
            else:
                print("  prefix with 'A:' or 'B:'")
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        stop.set()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("test")
    sub.add_parser("chat")
    sp = sub.add_parser("send")
    sp.add_argument("text")
    sp.add_argument("--from", dest="side", choices=["A", "B"], default="A")
    sl = sub.add_parser("listen")
    sl.add_argument("--on", dest="side", choices=["A", "B"], default="B")
    args = p.parse_args()

    a = open_port(PORT_A)
    b = open_port(PORT_B)
    try:
        if args.cmd == "test":
            return cmd_test(a, b)
        if args.cmd == "chat":
            return cmd_chat(a, b)
        if args.cmd == "send":
            return cmd_send(a if args.side == "A" else b, args.text)
        if args.cmd == "listen":
            return cmd_listen(a if args.side == "A" else b)
    finally:
        a.close()
        b.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())
