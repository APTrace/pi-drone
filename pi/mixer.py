"""Quad-X mixer: turns (throttle, roll, pitch, yaw) into 4 motor duties.

Top view, nose up:          Spin directions:          Sign convention (same as the ground station):
    FL     FR                 FL = CW   FR = CCW         roll  + = bank right
       \\ /                    RL = CCW  RR = CW          pitch + = nose down / forward
       / \\                                               yaw   + = turn right (clockwise from above)
    RL     RR

The four recipes (each motor = throttle +/- each correction):
    FL = T + r - p - y      left side up for roll+, front eases off for pitch+, CW prop slows for yaw+
    FR = T - r - p + y
    RL = T + r + p + y
    RR = T - r + p - y

Each correction is "balanced": it adds as much on two motors as it removes on the other two.
So turning one knob changes only that motion and leaves total lift and the other two motions alone.
`feel()` below measures this from the motor values; the tests use it to prove it.

Saturation policy ("attitude beats altitude"):
    1. If the corrections need more range than a motor has (spread > 1), shrink the corrections
       until they fit. Rare; only with large stick + PID demands.
    2. If a motor wants more than 1, shift ALL FOUR down by the same amount. The differences
       (= roll / pitch / yaw) survive; only a bit of total lift is lost.
    3. If a motor wants less than 0, clip it to 0. We deliberately do NOT shift up here: that
       would add thrust the pilot didn't ask for, e.g. at zero throttle on the ground ("air mode").
       That is a separate, later decision.
    Not armed -> all motors 0, whatever the inputs.

Pure logic, no hardware: the output is just 4 floats in [0, 1].
"""

from pi.safety import SafeCommand

MOTORS = ("FL", "FR", "RL", "RR")

# One row per motor: how much (roll, pitch, yaw) push it.  Throttle is +1 for everyone.
_SIGNS = (
    (+1, -1, -1),   # FL
    (-1, -1, +1),   # FR
    (+1, +1, +1),   # RL
    (-1, +1, -1),   # RR
)

OFF = (0.0, 0.0, 0.0, 0.0)


def _raw(t, r, p, y):
    """The four recipes, no limits applied."""
    return [t + sr * r + sp * p + sy * y for sr, sp, sy in _SIGNS]


def mix_clip(t, r, p, y):
    """Naive version: compute and clip each motor to [0, 1]. Kept only to show (in the tests)
    why this is wrong: clipping one motor breaks the balance between the four."""
    return tuple(min(1.0, max(0.0, m)) for m in _raw(t, r, p, y))


def mix(safe: SafeCommand):
    """The real mixer. Returns (FL, FR, RL, RR) duties, each in [0, 1]."""
    if not safe.armed:
        return OFF
    t, r, p, y = safe.throttle, safe.roll, safe.pitch, safe.yaw

    # 1. Corrections alone (throttle removed) must fit in a range of width 1.
    corr = _raw(0.0, r, p, y)
    spread = max(corr) - min(corr)
    if spread > 1.0:
        k = 1.0 / spread
        corr = [c * k for c in corr]

    m = [t + c for c in corr]

    # 2. Top saturation: shift everything down together.
    top = max(m)
    if top > 1.0:
        m = [v - (top - 1.0) for v in m]

    # 3. Bottom: clip (no shifting up — see module docstring).
    return tuple(max(0.0, min(1.0, v)) for v in m)


def feel(motors):
    """Inverse view: what (throttle, roll, pitch, yaw) do these 4 motor values actually produce?
        throttle = average of all four
        roll     = (left - right) / 4
        pitch    = (rear - front) / 4
        yaw      = (CCW pair - CW pair) / 4
    For unsaturated motors this gives back exactly the inputs of mix()."""
    fl, fr, rl, rr = motors
    return (
        (fl + fr + rl + rr) / 4,
        ((fl + rl) - (fr + rr)) / 4,
        ((rl + rr) - (fl + fr)) / 4,
        ((fr + rl) - (fl + rr)) / 4,
    )
