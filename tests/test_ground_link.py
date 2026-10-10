"""Tests for common/ground_link.py.

Run from the repo root:   python -m tests.test_ground_link
(Written as plain test_* functions, so pytest can also run them later.)
"""

import struct

from common.ground_link import PACKET_SIZE, Command, decode, encode


def test_size():
    assert PACKET_SIZE == 26


def test_round_trip():
    # Values chosen to be exactly representable in float32 (see test_float32_rounding)
    cmd = Command(throttle=0.5, roll=-0.25, pitch=0.125, yaw=0.0,
                  arm=True, kill=False, session=4242, seq=17)
    assert decode(encode(cmd)) == cmd


def test_float32_rounding():
    # 0.1 has no exact binary representation; float32 keeps ~7 significant digits
    back = decode(encode(Command(throttle=0.1)))
    assert back.throttle != 0.1
    assert abs(back.throttle - 0.1) < 1e-7


def test_clamping():
    back = decode(encode(Command(throttle=3.0, roll=-7.0)))
    assert back.throttle == 1.0
    assert back.roll == -1.0


def test_rejects_nan():
    assert decode(encode(Command(throttle=float("nan")))) is None


def test_rejects_wrong_length():
    good = encode(Command())
    assert decode(good[:-1]) is None
    assert decode(good + b"\x00") is None


def test_rejects_wrong_magic():
    good = encode(Command())
    assert decode(b"XX" + good[2:]) is None


def test_rejects_unknown_flags():
    good = bytearray(encode(Command()))
    good[3] = 0b100              # byte 3 = flags; bit 2 isn't defined
    assert decode(bytes(good)) is None


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.\n")

    # A peek at what actually travels over Wi-Fi
    cmd = Command(throttle=0.5, roll=-0.25, arm=True, session=4242, seq=17)
    raw = encode(cmd)
    print(f"Command : {cmd}")
    print(f"Packet  : {raw.hex(' ')}  ({len(raw)} bytes)")
    print(f"0.1 as float32 comes back as {decode(encode(Command(throttle=0.1))).throttle!r}")
