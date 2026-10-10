"""Tests for ground/controls.py.   Run from the repo root:   python -m tests.test_controls"""

from ground.controls import Controls, Inputs

DT = 0.02   # one frame at 50 Hz


def run(c, inp, frames):
    for _ in range(frames):
        cmd = c.update(inp, DT)
    return cmd


def test_throttle_ramps_and_holds():
    c = Controls(session=1)
    cmd = run(c, Inputs(throttle_dir=+1), 50)          # 1 s of W
    assert abs(cmd.throttle - 0.5) < 1e-9
    cmd = run(c, Inputs(), 50)                          # release: stays
    assert abs(cmd.throttle - 0.5) < 1e-9


def test_throttle_clamped():
    c = Controls(session=1)
    assert run(c, Inputs(throttle_dir=+1), 500).throttle == 1.0
    assert run(c, Inputs(throttle_dir=-1), 500).throttle == 0.0


def test_big_dt_is_capped():
    c = Controls(session=1)
    cmd = c.update(Inputs(throttle_dir=+1), dt=5.0)     # 5 s freeze with W held
    assert cmd.throttle <= 0.05 + 1e-9


def test_arm_only_at_zero_throttle():
    c = Controls(session=1)
    run(c, Inputs(throttle_dir=+1), 10)
    assert run(c, Inputs(arm=True), 1).arm is False
    run(c, Inputs(throttle_dir=-1), 100)
    assert run(c, Inputs(arm=True), 1).arm is True


def test_kill_latches_until_rearm():
    c = Controls(session=1)
    run(c, Inputs(arm=True), 1)
    run(c, Inputs(throttle_dir=+1), 25)
    cmd = run(c, Inputs(kill=True), 1)
    assert cmd.kill and not cmd.arm and cmd.throttle == 0.0
    assert run(c, Inputs(), 10).kill is True            # stays latched after release
    cmd = run(c, Inputs(arm=True), 1)
    assert cmd.arm and not cmd.kill


def test_seq_increments():
    c = Controls(session=7)
    a, b = c.update(Inputs(), DT), c.update(Inputs(), DT)
    assert (a.seq, b.seq, b.session) == (1, 2, 7)


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.")
