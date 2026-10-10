"""Tests for ground/sender.py.   Run from the repo root:   python -m tests.test_sender

The first four tests check the rules (pure function, instant).
The last one runs the real thread against a real UDP socket on this computer (~2 s).
"""

import socket
import time

from common.ground_link import Command, decode
from ground.sender import UI_DEAD, UI_STALE, Sender, outgoing

CMD = Command(throttle=0.4, roll=0.3, pitch=-0.3, yaw=0.3, arm=True, session=9)


def close(a, b):
    """Equal within float32 precision (0.3 travels as 0.30000001192..., see test_float32_rounding)."""
    return abs(a - b) < 1e-6


def test_fresh_ui_sends_command_unchanged():
    assert outgoing(CMD, ui_age=0.01) == CMD


def test_stale_ui_centres_sticks_keeps_throttle():
    out = outgoing(CMD, ui_age=(UI_STALE + UI_DEAD) / 2)
    assert (out.roll, out.pitch, out.yaw) == (0.0, 0.0, 0.0)
    assert out.throttle == 0.4 and out.arm is True


def test_dead_ui_sends_nothing():
    assert outgoing(CMD, ui_age=UI_DEAD + 0.01) is None


def test_nothing_published_yet_sends_nothing():
    assert outgoing(None, ui_age=0.0) is None


def test_thread_keeps_sending_then_goes_quiet():
    # A receiving socket on this same computer ("127.0.0.1" = loopback, never leaves the PC).
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))              # port 0 = "any free port"
    rx.settimeout(0.05)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sender = Sender(tx, rx.getsockname(), rate=50)
    sender.start()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.3:  # an "alive" UI: publishes every 10 ms for 0.3 s
        sender.publish(CMD)
        time.sleep(0.01)
    last_publish = time.perf_counter()     # ...then the UI "freezes" for good

    got = []
    while time.perf_counter() - last_publish < UI_DEAD + 0.5:
        try:
            data, _ = rx.recvfrom(64)
            got.append((time.perf_counter(), decode(data)))
        except socket.timeout:
            pass
    sender.stop()

    seqs = [c.seq for _, c in got]
    assert seqs == list(range(1, len(seqs) + 1)), "seq must count 1, 2, 3, ... with no holes"
    assert any(close(c.roll, 0.3) for _, c in got), "fresh phase: sticks as published"
    assert any(c.roll == 0.0 for _, c in got), "stale phase: sticks centred"
    assert all(close(c.throttle, 0.4) for _, c in got), "throttle held throughout"
    last_arrival = got[-1][0]
    assert last_arrival - last_publish < UI_DEAD + 0.1, "must go quiet once the UI is dead"
    print(f"      ({len(got)} packets; went quiet {last_arrival - last_publish:.2f} s after the UI froze)")


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.")
