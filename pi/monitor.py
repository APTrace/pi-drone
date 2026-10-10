"""Step 1b test harness (Pi): the real receiver + safety running in a fixed-rate loop, shown live.

Run from the repo root:   python3 -m pi.monitor        (Ctrl+C to stop)

This loop is a rehearsal of the 1c control loop: same three lines at its heart,
    receiver.poll() -> receiver.latest() -> safety.update()
and the same rules: never block, never wait on the network, print only occasionally.
"""

import math
import time

from pi.receiver import CommandReceiver
from pi.safety import SafetyManager

RATE = 50              # loop iterations per second
DISPLAY_EVERY = 5      # refresh the status line every 5th iteration (10 Hz)


def main() -> None:
    receiver = CommandReceiver()
    safety = SafetyManager()
    period = 1.0 / RATE
    start = time.monotonic()
    next_t = start
    i = 0
    print(f"Monitor running at {RATE} Hz. Waiting for the ground station... (Ctrl+C to stop)")
    try:
        while True:
            # ---- the three lines that 1c will reuse unchanged ----
            receiver.poll()
            cmd, age = receiver.latest()
            safe = safety.update(cmd, age, time.monotonic())

            # ---- display: events get their own line, status line rewrites itself ----
            for event in safety.pop_events():
                # ljust pads with spaces so the event fully overwrites the old status line
                print("\r" + f"[{time.monotonic() - start:7.2f} s] {event}".ljust(64))
            if i % DISPLAY_EVERY == 0:
                link = "  none" if math.isinf(age) else f"{age * 1000:5.0f}ms"
                print(
                    f"\r{safety.state:<16} link{link} "
                    f"T{safe.throttle:.2f} R{safe.roll:+.2f} P{safe.pitch:+.2f} Y{safe.yaw:+.2f} "
                    f"{'ARMED' if safe.armed else 'off  '}",
                    end="", flush=True,
                )
            i += 1

            # ---- hold the rate on an absolute timeline (same trick as the sender thread) ----
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()
    except KeyboardInterrupt:
        print(f"\nStopped. Packets: {receiver.accepted} accepted, {receiver.rejected} rejected, "
              f"{receiver.out_of_order} out of order.")
    finally:
        receiver.close()


if __name__ == "__main__":
    main()
