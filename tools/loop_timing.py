"""Step 1c-3: how steady is the flight loop on the Pi?  (the "timing gate")

Run from the repo root (Pi):
    python3 -m tools.loop_timing --rate 500 --seconds 30
    python3 -m tools.loop_timing --rate 1000 --seconds 30
    python3 -m tools.loop_timing --rate 1000 --seconds 30 --gc off      # garbage collector off
    python3 -m tools.loop_timing --rate 1000 --seconds 30 --chatty      # print EVERY iteration (bad on purpose)

It runs the real 1c-2 flight loop (real receiver + safety + fake IMU + controller + mixer + fake motors)
as fast as asked, with NO display, and measures two different things per iteration:

    period = time from the start of one iteration to the start of the next.
             Ideal: exactly 1/rate. This is what the drone "feels": a late period = a late correction.
    work   = how long loop.step() itself took (the actual computing).
             Must stay well below the period, or the loop can't keep up at all.

    |<------------------ period ------------------>|
    |== work ==|...........sleep...................|== work ==|...
    ^ iteration starts                             ^ next one starts (ideally on the beat)

A long period with short work means "something else stole the CPU" (Linux, the garbage collector,
Wi-Fi interrupts...). A long work time means "our own code is too slow".
Same lesson as the Wi-Fi link: the median will look perfect, the TAIL is what matters.
"""

import argparse
import gc
import time
from array import array

from pi.attitude import PassThroughController
from pi.fakes import FakeIMU, FakeMotors
from pi.flight_loop import FlightLoop
from pi.safety import SafetyManager


class GCWatch:
    """Counts garbage-collector runs during the test and times the longest one.
    Python calls these callbacks itself, before and after every collection."""

    def __init__(self):
        self.count = 0
        self.longest = 0.0
        self._t0 = 0.0

    def __call__(self, phase, info):
        if phase == "start":
            self._t0 = time.perf_counter()
        else:
            self.count += 1
            self.longest = max(self.longest, time.perf_counter() - self._t0)


def percentile(sorted_ms, p):
    return sorted_ms[min(len(sorted_ms) - 1, int(p / 100 * len(sorted_ms)))]


def report(name, values, ideal_ms, buckets):
    ms = sorted(v * 1000 for v in values)
    n = len(ms)
    print(f"\n{name}: {n} samples   median {percentile(ms, 50):.3f} ms   "
          f"99th {percentile(ms, 99):.3f}   99.9th {percentile(ms, 99.9):.3f}   max {ms[-1]:.3f} ms")
    edges = [b * ideal_ms for b in buckets]
    labels = [f"< {buckets[0]}x"] + [f"{a}-{b}x" for a, b in zip(buckets, buckets[1:])] + [f"> {buckets[-1]}x"]
    counts = [0] * (len(edges) + 1)
    for v in ms:
        k = 0
        while k < len(edges) and v >= edges[k]:
            k += 1
        counts[k] += 1
    biggest = max(counts)
    for label, c in zip(labels, counts):
        bar = "#" * (round(40 * c / biggest) if c else 0)
        if c and not bar:
            bar = "|"                                  # rare but present: still show something
        print(f"   {label:>10} period  {c:8d}  {bar}")


def main() -> None:
    ap = argparse.ArgumentParser(description="1c-3 loop timing experiment")
    ap.add_argument("--rate", type=int, default=500, help="loop iterations per second")
    ap.add_argument("--seconds", type=float, default=30.0, help="how long to run")
    ap.add_argument("--gc", choices=("on", "off"), default="on", help="garbage collector during the run")
    ap.add_argument("--chatty", action="store_true", help="print a line every iteration (perturbation test)")
    args = ap.parse_args()

    from pi.receiver import CommandReceiver
    receiver = CommandReceiver()
    loop = FlightLoop(receiver, SafetyManager(), FakeIMU(), PassThroughController(), FakeMotors())

    period = 1.0 / args.rate
    n = int(args.rate * args.seconds)
    periods = array("d", bytes(8 * n))       # allocated ONCE up front: no growing lists in the hot loop
    works = array("d", bytes(8 * n))

    watch = GCWatch()
    gc.callbacks.append(watch)
    if args.gc == "off":
        gc.disable()

    print(f"Loop timing: {args.rate} Hz ({period * 1000:.3f} ms period) for {args.seconds:.0f} s, "
          f"gc {args.gc}{', chatty' if args.chatty else ''}. Don't touch anything...")
    now = time.perf_counter()
    next_t = now
    prev = now
    resyncs = 0
    try:
        for i in range(n):
            start = time.perf_counter()
            periods[i] = start - prev
            prev = start
            loop.step(time.monotonic())
            works[i] = time.perf_counter() - start
            if args.chatty:
                print(f"{i} {loop.duties}")
            elif i % args.rate == 0:
                print(f"\r  {i // args.rate:4d} s", end="", flush=True)

            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()
                resyncs += 1
    except KeyboardInterrupt:
        n = i
        print("\n(stopped early)")
    finally:
        gc.enable()
        gc.callbacks.remove(watch)
        receiver.close()

    ideal_ms = period * 1000
    report("PERIOD (start to start)", periods[1:n], ideal_ms, [0.9, 1.1, 1.5, 2, 5, 10])
    report("WORK   (inside loop.step)", works[:n], ideal_ms, [0.1, 0.25, 0.5, 1])
    late = sum(1 for p in periods[1:n] if p > 2 * period)
    over = sum(1 for w in works[:n] if w > period)
    print(f"\nperiods > 2x ideal: {late}   ({late / max(1, n - 1) * 100:.3f} %)")
    print(f"work > 1 period (couldn't keep up at all): {over}")
    print(f"resyncs (loop fell behind its timeline): {resyncs}")
    print(f"garbage collections during the run: {watch.count}, longest {watch.longest * 1000:.3f} ms")
    print(f"motor writes: {loop.motors.writes} (should equal iterations: {n})")


if __name__ == "__main__":
    main()
