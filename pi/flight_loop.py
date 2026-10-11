"""Step 1c-2: the flight-control loop skeleton, with fake IMU and fake motors.

Run from the repo root (Pi):   python3 -m pi.flight_loop [--rate 50]      (Ctrl+C to stop)

One iteration = the whole drone, in order:
    1. receiver.poll / latest      what did the pilot ask for, and how old is it?
    2. safety.update               what is the drone ALLOWED to do?             -> SafeCommand
    3. imu.read                    where is the drone pointing right now?      -> Attitude
    4. controller.update           corrections needed                          -> roll, pitch, yaw
    5. mix                         corrections -> 4 motor duties               -> FL, FR, RL, RR
    6. motors.write                every iteration, even disarmed (= heartbeat for the Pico)

Every part is passed in from outside ("plugged in"), so tests can use fakes and the real
hardware drivers can replace the fakes later without touching this file.
"""

import argparse
import math
import time

from common.gapstats import summarize
from pi.attitude import PassThroughController
from pi.fakes import FakeIMU, FakeMotors
from pi.mixer import MOTORS, mix
from pi.safety import SafeCommand, SafetyManager


class FlightLoop:
    """The six steps above, as one method. No clock, no sleeping, no printing: pure plumbing."""

    def __init__(self, receiver, safety, imu, controller, motors):
        self.receiver = receiver
        self.safety = safety
        self.imu = imu
        self.controller = controller
        self.motors = motors
        self._last_t = None
        # Kept for the display:
        self.safe = SafeCommand()
        self.duties = (0.0, 0.0, 0.0, 0.0)
        self.age = math.inf

    def step(self, now: float) -> None:
        dt = 0.0 if self._last_t is None else now - self._last_t
        self._last_t = now

        self.receiver.poll()                                          # 1
        cmd, self.age = self.receiver.latest()
        self.safe = self.safety.update(cmd, self.age, now)            # 2
        attitude = self.imu.read(now)                                 # 3
        roll, pitch, yaw = self.controller.update(self.safe, attitude, dt)   # 4
        corrected = SafeCommand(throttle=self.safe.throttle, roll=roll, pitch=pitch,
                                yaw=yaw, armed=self.safe.armed)
        self.duties = mix(corrected)                                  # 5
        self.motors.write(self.duties)                                # 6


def _bar(x: float, width: int = 6) -> str:
    """0.62 -> "████··" : a tiny text bar so motor changes are visible at a glance."""
    n = round(max(0.0, min(1.0, x)) * width)
    return "█" * n + "·" * (width - n)


def main() -> None:
    parser = argparse.ArgumentParser(description="1c-2 flight loop skeleton (fake IMU + motors)")
    parser.add_argument("--rate", type=int, default=50, help="loop iterations per second")
    args = parser.parse_args()

    from pi.receiver import CommandReceiver      # imported here so tests never open a socket
    receiver = CommandReceiver()
    loop = FlightLoop(receiver, SafetyManager(), FakeIMU(), PassThroughController(), FakeMotors())

    period = 1.0 / args.rate
    display_every = max(1, args.rate // 10)       # status line at ~10 Hz whatever the loop rate
    start = time.monotonic()
    next_t = start
    prev = None
    gaps = []                                      # iteration-to-iteration times (preview of 1c-3)
    i = 0
    print(f"Flight loop at {args.rate} Hz (fake IMU, fake motors). Ctrl+C to stop.")
    try:
        while True:
            now = time.monotonic()
            if prev is not None:
                gaps.append(now - prev)
            prev = now

            loop.step(now)

            for event in loop.safety.pop_events():
                print("\r" + f"[{now - start:7.2f} s] {event}".ljust(78))
            if i % display_every == 0:
                m = "  ".join(f"{name} {_bar(d)} {d:.2f}" for name, d in zip(MOTORS, loop.duties))
                print(f"\r{loop.safety.state:<9} {m}", end="", flush=True)
            i += 1

            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()
    except KeyboardInterrupt:
        print(f"\nStopped after {i} iterations; motors written {loop.motors.writes} times "
              f"(should be equal: heartbeat every iteration).")
        summarize(gaps, label=f"loop periods (ideal {period * 1000:.1f} ms)")
    finally:
        receiver.close()


if __name__ == "__main__":
    main()
