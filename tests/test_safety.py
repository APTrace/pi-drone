"""Tests for pi/safety.py.   Run from the repo root:   python -m tests.test_safety  (Windows or Pi)

Every test drives the SafetyManager with fake times, so a 3-second landing takes microseconds.
"""

from common.ground_link import Command
from pi.safety import DESCEND_AFTER, DESCENT_TIME, LEVEL_AFTER, OFF, SafetyManager

FRESH = 0.02   # link age of a normal, fresh packet


def cmd(**kw):
    base = dict(throttle=0.0, roll=0.0, pitch=0.0, yaw=0.0, arm=False, kill=False, session=1, seq=0)
    base.update(kw)
    return Command(**base)


def armed_manager():
    """A SafetyManager that went through the proper arming sequence."""
    s = SafetyManager()
    s.update(cmd(arm=False), FRESH, 0.0)          # release seen
    s.update(cmd(arm=True), FRESH, 0.0)           # requested at zero throttle
    assert s.armed
    return s


def test_no_link_means_off():
    s = SafetyManager()
    assert s.update(None, float("inf"), 0.0) == OFF


def test_boot_needs_release_before_arming():
    s = SafetyManager()
    s.update(cmd(arm=True), FRESH, 0.0)           # arm already "on" when the Pi started listening
    assert not s.armed
    s.update(cmd(arm=False), FRESH, 0.0)
    s.update(cmd(arm=True), FRESH, 0.0)
    assert s.armed


def test_arm_refused_unless_throttle_zero():
    s = SafetyManager()
    s.update(cmd(arm=False), FRESH, 0.0)
    assert s.update(cmd(arm=True, throttle=0.1), FRESH, 0.0) == OFF
    assert not s.armed


def test_arm_refused_on_stale_link():
    s = SafetyManager()
    s.update(cmd(arm=False), FRESH, 0.0)
    s.update(cmd(arm=True), LEVEL_AFTER + 0.1, 0.0)
    assert not s.armed


def test_armed_passes_command_through():
    s = armed_manager()
    out = s.update(cmd(arm=True, throttle=0.5, roll=0.3), FRESH, 1.0)
    assert out.armed and out.throttle == 0.5 and out.roll == 0.3


def test_disarm_request():
    s = armed_manager()
    assert s.update(cmd(arm=False, throttle=0.5), FRESH, 1.0) == OFF
    assert not s.armed


def test_kill_is_instant_and_latched():
    s = armed_manager()
    s.update(cmd(arm=True, throttle=0.6), FRESH, 1.0)
    assert s.update(cmd(arm=True, throttle=0.6, kill=True), FRESH, 1.0) == OFF
    # still killed if arm stays requested without a release
    assert s.update(cmd(arm=True, throttle=0.0), FRESH, 1.1) == OFF


def test_rearm_after_kill_like_the_ground_station_does_it():
    s = armed_manager()
    s.update(cmd(arm=False, kill=True), FRESH, 1.0)    # SPACE: ground sends arm=False, kill=True
    s.update(cmd(arm=True, kill=False), FRESH, 1.1)    # E at zero throttle
    assert s.armed


def test_level_stage_centres_sticks_holds_throttle():
    s = armed_manager()
    s.update(cmd(arm=True, throttle=0.5, roll=0.3), FRESH, 1.0)
    out = s.update(cmd(arm=True, throttle=0.5, roll=0.3), (LEVEL_AFTER + DESCEND_AFTER) / 2, 1.5)
    assert s.state == "LEVEL"
    assert out.armed and out.throttle == 0.5 and (out.roll, out.pitch, out.yaw) == (0, 0, 0)


def test_level_recovers_when_link_returns():
    s = armed_manager()
    c = cmd(arm=True, throttle=0.5, roll=0.3)
    s.update(c, 0.5, 1.0)
    out = s.update(c, FRESH, 1.1)
    assert s.state == "ARMED" and out.roll == 0.3


def test_descent_ramps_down_then_disarms():
    s = armed_manager()
    c = cmd(arm=True, throttle=0.6)
    s.update(c, FRESH, 10.0)
    t0 = 10.0 + DESCEND_AFTER + 0.01
    first = s.update(c, DESCEND_AFTER + 0.01, t0)
    half = s.update(c, DESCEND_AFTER + 1.0, t0 + DESCENT_TIME / 2)
    assert s.state == "DESCEND"
    assert abs(first.throttle - 0.6) < 1e-9
    assert abs(half.throttle - 0.3) < 1e-9 and half.roll == 0.0
    assert s.update(c, 5.0, t0 + DESCENT_TIME) == OFF
    assert not s.armed


def test_descent_is_one_way_even_if_link_returns():
    s = armed_manager()
    c = cmd(arm=True, throttle=0.6)
    s.update(c, FRESH, 0.0)
    s.update(c, DESCEND_AFTER + 0.01, 1.0)              # descent starts
    out = s.update(c, FRESH, 1.5)                        # link is back...
    assert s.state == "DESCEND" and out.throttle < 0.6  # ...but landing continues


def test_no_auto_rearm_after_failsafe_landing():
    s = armed_manager()
    c = cmd(arm=True, throttle=0.0)
    s.update(c, DESCEND_AFTER + 0.01, 0.0)
    s.update(c, 3.0, DESCENT_TIME + 0.01)               # landed and disarmed
    assert s.update(c, FRESH, 5.0) == OFF                # link back, arm still held: NOT re-armed
    s.update(cmd(arm=False), FRESH, 5.1)                 # Q
    s.update(cmd(arm=True), FRESH, 5.2)                  # E
    assert s.armed


def test_kill_during_descent():
    s = armed_manager()
    c = cmd(arm=True, throttle=0.6)
    s.update(c, DESCEND_AFTER + 0.01, 0.0)
    assert s.update(cmd(arm=False, kill=True), FRESH, 0.5) == OFF


def test_new_session_disarms():
    s = armed_manager()
    assert s.update(cmd(arm=True, session=2), FRESH, 1.0) == OFF
    assert not s.armed


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"All {len(tests)} tests passed.")
