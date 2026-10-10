"""Tiny statistics helper for timing gaps (used by udp_peek on the Pi and by the ground station)."""


def summarize(gaps: list[float], label: str = "gaps") -> None:
    """Print the distribution of time gaps (in seconds). Ideal at 50 Hz: 20 ms each."""
    if not gaps:
        return
    ms = sorted(g * 1000 for g in gaps)
    n = len(ms)

    def pct(p):                       # p-th percentile: the value p % of gaps are below
        return ms[min(n - 1, int(p / 100 * n))]

    print(f"{label}: {n} gaps over {sum(ms) / 1000:.0f} s:  median {pct(50):.0f} ms   "
          f"99th pct {pct(99):.0f} ms   max {ms[-1]:.0f} ms")
    for limit in (50, 100, 150, 200):
        count = sum(1 for g in ms if g > limit)
        print(f"   gaps > {limit:3d} ms: {count}")
