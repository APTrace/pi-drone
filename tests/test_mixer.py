"""Tests for pi/mixer.py.   Run from the repo root:   python -m tests.test_mixer  (Windows or Pi)

Most tests use feel(): "measure what the drone would feel" from the 4 motor values,
and check it against what was asked for.
"""

from pi.mixer import OFF, feel, mix, mix_clip
from pi.safety import SafeCommand

TOL = 1e-9


def sc(throttle=0.5, roll=0.0, pitch=0.0, yaw=0.0, armed=True):
    return SafeCommand(throttle=throttle, roll=roll, pitch=pitch, yaw=yaw, armed=armed)


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_disarmed_is_off():
    assert mix(sc(throttle=0.8, roll=0.3, armed=False)) == OFF


def test_throttle_only_all_equal():
    assert close(mix(sc(throttle=0.4)), (0.4, 0.4, 0.4, 0.4))


def test_roll_right_left_motors_push():
    fl, fr, rl, rr = mix(sc(roll=0.1))
    assert fl > fr and rl > rr                      # left side up -> drone banks right
    assert close((fl, fr, rl, rr), (0.6, 0.4, 0.6, 0.4))


def test_pitch_forward_rear_motors_push():
    fl, fr, rl, rr = mix(sc(pitch=0.1))
    assert rl > fl and rr > fr                      # rear up -> nose down


def test_yaw_right_ccw_props_speed_up():
    fl, fr, rl, rr = mix(sc(yaw=0.1))
    assert fr > fl and rl > rr                      # CCW pair (FR, RL) faster -> body turns clockwise


def test_each_knob_moves_only_itself():
    """The 'balanced recipes' property: one knob in, only that knob comes out."""
    for knob in ("roll", "pitch", "yaw"):
        asked = sc(**{knob: 0.15})
        felt = feel(mix(asked))
        expected = (asked.throttle, asked.roll, asked.pitch, asked.yaw)
        assert close(felt, expected), (knob, felt)


def test_mixed_inputs_round_trip():
    asked = sc(throttle=0.5, roll=0.1, pitch=-0.05, yaw=0.08)
    assert close(feel(mix(asked)), (0.5, 0.1, -0.05, 0.08))


def test_outputs_always_in_range():
    for t in (0.0, 0.3, 0.9, 1.0):
        for v in (-1.0, -0.3, 0.0, 0.3, 1.0):
            for m in mix(sc(throttle=t, roll=v, pitch=-v, yaw=v)):
                assert 0.0 <= m <= 1.0


def test_why_plain_clipping_is_wrong():
    """High throttle + full roll: FL/RL want 1.2. Clipping loses roll; shift-to-fit keeps it."""
    asked = sc(throttle=0.9, roll=0.3)
    clipped = feel(mix_clip(0.9, 0.3, 0.0, 0.0))
    shifted = feel(mix(asked))
    assert clipped[1] < 0.3 - 0.05                  # clipping: roll badly reduced (0.2 instead of 0.3)
    assert abs(shifted[1] - 0.3) < TOL              # shift-to-fit: full roll delivered
    assert shifted[0] < 0.9                         # ...paid for with a little throttle


def test_low_end_does_not_add_thrust():
    """At zero throttle the mixer must never lift the total above what was asked."""
    m = mix(sc(throttle=0.0, roll=0.3))
    assert feel(m)[0] <= 0.3 / 2 + TOL              # only the clipped half survives, nothing shifted up
    assert min(m) == 0.0


def test_huge_corrections_are_scaled_not_lost():
    """Corrections needing more than full range get shrunk, but keep their direction."""
    fl, fr, rl, rr = mix(sc(throttle=0.5, roll=1.0, pitch=1.0))
    _, roll, pitch, _ = feel((fl, fr, rl, rr))
    assert roll > 0 and pitch > 0


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.")
