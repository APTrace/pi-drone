"""Tests for pi/receiver.py.   Run from the repo root:   python -m tests.test_receiver

Uses real UDP sockets on 127.0.0.1 (loopback: packets never leave this computer).
"""

import math
import socket
import time

from common.ground_link import Command, encode
from pi.receiver import CommandReceiver

PORT = 15005   # a test port, so it doesn't clash with a real monitor running on 5005


def make():
    rx = CommandReceiver(port=PORT, host="127.0.0.1")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return rx, tx


def send(tx, **kw):
    tx.sendto(encode(Command(**kw)), ("127.0.0.1", PORT))


def test_nothing_yet():
    rx, tx = make()
    try:
        rx.poll()
        cmd, age = rx.latest()
        assert cmd is None and math.isinf(age)
    finally:
        rx.close()


def test_poll_never_blocks():
    rx, tx = make()
    try:
        t0 = time.perf_counter()
        for _ in range(1000):
            rx.poll()                          # empty socket, 1000 times
        assert time.perf_counter() - t0 < 0.5, "poll() must return immediately when nothing is waiting"
    finally:
        rx.close()


def test_keeps_only_newest_of_a_burst():
    rx, tx = make()
    try:
        for seq in (1, 2, 3):
            send(tx, session=5, seq=seq, throttle=seq / 10)
        time.sleep(0.05)
        rx.poll()
        cmd, age = rx.latest()
        assert cmd.seq == 3 and rx.accepted == 3 and age < 0.1
    finally:
        rx.close()


def test_out_of_order_ignored():
    rx, tx = make()
    try:
        send(tx, session=5, seq=10)
        send(tx, session=5, seq=9)             # late arrival
        time.sleep(0.05)
        rx.poll()
        assert rx.latest()[0].seq == 10 and rx.out_of_order == 1
    finally:
        rx.close()


def test_new_session_accepted_even_with_lower_seq():
    rx, tx = make()
    try:
        send(tx, session=5, seq=500)
        send(tx, session=6, seq=1)             # ground station restarted
        time.sleep(0.05)
        rx.poll()
        assert rx.latest()[0].session == 6
    finally:
        rx.close()


def test_garbage_rejected():
    rx, tx = make()
    try:
        tx.sendto(b"hello drone", ("127.0.0.1", PORT))
        time.sleep(0.05)
        rx.poll()
        assert rx.latest()[0] is None and rx.rejected == 1
    finally:
        rx.close()


def test_age_grows():
    rx, tx = make()
    try:
        send(tx, session=5, seq=1)
        time.sleep(0.05)
        rx.poll()
        a1 = rx.latest()[1]
        time.sleep(0.1)
        rx.poll()                              # nothing new arrived
        a2 = rx.latest()[1]
        assert a2 - a1 > 0.09
    finally:
        rx.close()


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.")
