"""Turns 'what the pilot is pressing' into a Command. Pure logic: no pygame, no sockets.

Why a separate file? Same reason as safety.py on the Pi: logic you can unit-test without
a window or a network. It also means a gamepad later only needs to produce `Inputs`;
everything below stays untouched.

Sign convention (to be checked against the mixer in step 1c):
    roll  +  = bank right      pitch +  = nose down / fly forward      yaw + = turn right
"""

from dataclasses import dataclass

from common.ground_link import Command

THROTTLE_RATE = 0.5   # throttle change per second while W/S held -> 0 to full in 2 s
MAX_DT = 0.1          # cap on one time step (see update())


@dataclass(frozen=True)
class Inputs:
    """One snapshot of the input device, already in 'stick units'."""
    throttle_dir: int = 0    # +1 = W held, -1 = S held, 0 = neither (or both)
    roll: float = 0.0        # -1..1
    pitch: float = 0.0       # -1..1
    yaw: float = 0.0         # -1..1
    arm: bool = False        # arm button held
    disarm: bool = False     # disarm button held
    kill: bool = False       # kill button held


class Controls:
    """Holds the state that persists between frames: throttle position, arm request, kill latch."""

    def __init__(self, session: int):
        self.session = session
        self.throttle = 0.0
        self.arm = False
        self.kill = False
        self.message = "Disarmed. Throttle at 0, press E to arm."

    def update(self, inp: Inputs, dt: float) -> Command:
        # A frame can take unusually long (window dragged, first frame after start-up).
        # Without the cap, a held W during a 2 s freeze would jump throttle to 100 %.
        dt = min(dt, MAX_DT)

        if inp.kill:
            # Kill beats everything, every frame it's held.
            self.kill = True
            self.arm = False
            self.throttle = 0.0
            self.message = "KILL! Press E (at zero throttle) to clear and re-arm."
        else:
            # Throttle is INTEGRATED: it moves while a key is held and stays put on release.
            t = self.throttle + inp.throttle_dir * THROTTLE_RATE * dt
            self.throttle = max(0.0, min(1.0, t))   # clamping makes "exactly 0.0" reachable

            if inp.disarm and self.arm:
                self.arm = False
                self.message = "Disarm requested."
            if inp.arm and not self.arm:
                if self.throttle == 0.0:
                    self.arm = True
                    self.kill = False               # a fresh arm request clears the kill latch
                    self.message = "Arm requested."
                else:
                    self.message = "Can't arm: bring throttle to 0 first (hold S)."

        return Command(
            throttle=self.throttle,
            roll=inp.roll, pitch=inp.pitch, yaw=inp.yaw,   # sticks: passed through, they self-centre
            arm=self.arm, kill=self.kill,
            session=self.session,   # seq is filled in by the sender thread, one per packet
        )
