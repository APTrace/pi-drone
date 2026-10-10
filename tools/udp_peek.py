"""Debug tool (Pi): listen for ground-station packets and show them live on one line.

Run from the repo root:   python3 -m tools.udp_peek        (Ctrl+C to stop)

This is a quick look-through-the-window tool, NOT the real receiver: it BLOCKS while
waiting for packets, which is fine here but forbidden in the control loop. The real
receiver (pi/receiver.py, next piece) never waits.
"""

import socket
import time

from common.ground_link import DEFAULT_PORT, decode


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", DEFAULT_PORT))   # 0.0.0.0 = accept on every network interface
    sock.settimeout(0.5)                   # wake up twice a second even if nothing arrives
    print(f"Listening on UDP port {DEFAULT_PORT}... (Ctrl+C to stop)")

    good = bad = 0
    session = None
    last_arrival = None
    window_start = time.monotonic()
    window_count = 0
    window_max_gap = 0.0
    rate = 0.0
    shown_gap = 0.0
    last_print = 0.0
    try:
        while True:
            try:
                # Buffer bigger than 26 on purpose: an oversized packet arrives as >26 bytes
                # and decode() rejects it, instead of being silently cut to 26.
                data, addr = sock.recvfrom(64)
            except socket.timeout:
                if last_arrival is not None:
                    silent = time.monotonic() - last_arrival
                    print(f"\r  ... no packets for {silent:5.1f} s" + " " * 40, end="", flush=True)
                continue

            now = time.monotonic()
            cmd = decode(data)
            if cmd is None:
                bad += 1
                continue
            good += 1

            if cmd.session != session:
                session = cmd.session
                print(f"\nNew session {session} from {addr[0]}")

            if last_arrival is not None:
                window_max_gap = max(window_max_gap, now - last_arrival)
            last_arrival = now
            window_count += 1

            # Stats over 1-second windows (rate, worst gap); display refreshed 10x per second
            # so you can watch the keys live without flooding the SSH terminal.
            if now - window_start >= 1.0:
                rate = window_count / (now - window_start)
                shown_gap = window_max_gap
                window_start, window_count, window_max_gap = now, 0, 0.0
            if now - last_print >= 0.1:
                last_print = now
                flags = ("ARM " if cmd.arm else "--- ") + ("KILL" if cmd.kill else "----")
                print(
                    f"\r{rate:5.1f} Hz  gap max {shown_gap * 1000:4.0f} ms  seq {cmd.seq:6d}  "
                    f"T {cmd.throttle:.2f} R {cmd.roll:+.2f} P {cmd.pitch:+.2f} Y {cmd.yaw:+.2f}  "
                    f"{flags}  bad {bad}",
                    end="", flush=True,
                )
    except KeyboardInterrupt:
        print(f"\nStopped. {good} good packets, {bad} rejected.")


if __name__ == "__main__":
    main()
