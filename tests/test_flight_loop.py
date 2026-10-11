"""Tests for pi/flight_loop.py (plumbing only).   Run from the repo root:   python -m tests.test_flight_loop

The loop gets a FakeReceiver instead of a real socket, so the whole chain
    command -> safety -> IMU -> controller -> mixer -> motors
runs in microseconds, with fake times, on Windows or the Pi.
"""

import math

from common.ground_link import Command
from pi.attitude import PassThroughController
from pi.fakes import FakeIMU, FakeMotors
from pi.flight_loop import FlightLoop
from pi.safety import SafetyManager

FRESH = 0.02


class FakeReceiver:
    """Same plug shape as CommandReceiver: poll() and latest() -> (cmd, age)."""

    def __init__(self):
        self.cmd = None
        self.age = math.inf
        self.polls = 0

    def poll(self):
        self.polls += 1

    def latest(self):
        return self.cmd, self.age

    def send(self, **kw):
        base = dict(throttle=0.0, roll=0.0, pitch=0.0, yaw=0.0, arm=False, kill=False, session=1, seq=0)
        base.update(kw)
        self.cmd, self.age = Command(**base), FRESH


def make_loop():
    rx = FakeReceiver()
    loop = FlightLoop(rx, SafetyManager(), FakeIMU(), PassThroughController(), FakeMotors())
    return rx, loop


def arm(rx, loop, t=0.0):
    rx.send(arm=False)
    loop.step(t)
    rx.send(arm=True)
    loop.step(t + 0.02)
    assert loop.safety.armed                        # (the arming tick itself still outputs OFF)


def test_no_link_motors_off_but_still_written():
    rx, loop = make_loop()
    for k in range(10):
        loop.step(k * 0.02)
    assert loop.motors.last == (0.0, 0.0, 0.0, 0.0)
    assert loop.motors.writes == 10                 # heartbeat even with no link at all


def test_every_part_called_once_per_step():
    rx, loop = make_loop()
    for k in range(7):
        loop.step(k * 0.02)
    assert rx.polls == 7 and loop.imu.reads == 7 and loop.motors.writes == 7


def test_throttle_reaches_all_four_motors():
    rx, loop = make_loop()
    arm(rx, loop)
    rx.send(arm=True, throttle=0.4)
    loop.step(0.04)
    assert all(abs(d - 0.4) < 1e-6 for d in loop.motors.last)


def test_roll_right_keys_to_motors():
    """End-to-end sign check: roll+ from the pilot -> left motors faster than right motors."""
    rx, loop = make_loop()
    arm(rx, loop)
    rx.send(arm=True, throttle=0.5, roll=0.3)
    loop.step(0.04)
    fl, fr, rl, rr = loop.motors.last
    assert fl > fr and rl > rr


def test_link_loss_levels_then_lands_through_the_whole_chain():
    rx, loop = make_loop()
    arm(rx, loop)
    rx.send(arm=True, throttle=0.5, roll=0.3)
    loop.step(0.04)
    rx.age = 0.5                                    # link silent 0.5 s -> LEVEL: sticks centred
    loop.step(0.5)
    fl, fr, rl, rr = loop.motors.last
    assert abs(fl - fr) < 1e-6 and fl > 0           # roll gone, throttle held
    rx.age = 10.0                                   # link silent long enough to land
    for k in range(200):
        loop.step(1.0 + k * 0.02)
    assert loop.motors.last == (0.0, 0.0, 0.0, 0.0) and not loop.safety.armed


def test_kill_stops_motors_immediately():
    rx, loop = make_loop()
    arm(rx, loop)
    rx.send(arm=True, throttle=0.7)
    loop.step(0.04)
    rx.send(arm=False, kill=True)
    loop.step(0.06)
    assert loop.motors.last == (0.0, 0.0, 0.0, 0.0)


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.")
