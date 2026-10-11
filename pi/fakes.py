"""Stand-ins for hardware that hasn't arrived yet: an IMU and the motor output.

Each fake has exactly the "plug shape" the real part will have, so the flight loop never knows
the difference. When parts arrive:
    FakeIMU     -> pi/imu.py         (SPI driver + complementary filter, step 2)
    FakeMotors  -> pi/pico_out.py    (packets to the Pico over UART/SPI, step 3)
Same method names, same return types -> the loop doesn't change.

Plug shapes:
    imu.read(now)        -> Attitude      (where is the drone pointing, how fast is it turning)
    motors.write(duties) -> None          (4 duties in [0, 1]: FL, FR, RL, RR)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Attitude:
    """What the IMU (after filtering) tells the controller. Angles in degrees, rates in deg/s.
    roll + = right side down, pitch + = nose down, yaw_rate + = turning right (same signs as sticks)."""
    roll: float = 0.0
    pitch: float = 0.0
    yaw_rate: float = 0.0


LEVEL = Attitude()


class FakeIMU:
    """Pretends the drone sits perfectly level and still, forever.

    Deliberately dumb for now. Later this is where the 6-DOF simulator plugs in: it will take the
    motor duties, integrate the physics, and report the resulting attitude (software-in-the-loop).
    """

    def __init__(self):
        self.reads = 0

    def read(self, now: float) -> Attitude:
        self.reads += 1
        return LEVEL


class FakeMotors:
    """Pretends to send the 4 duties to the Pico. Records what it "sent" so tests and the display
    can look at it.

    Rule from the failsafe design: write() is called EVERY loop iteration, even when disarmed
    (all zeros). That steady stream is the heartbeat the Pico watchdog will listen for.
    """

    def __init__(self):
        self.writes = 0
        self.last = (0.0, 0.0, 0.0, 0.0)

    def write(self, duties) -> None:
        self.writes += 1
        self.last = tuple(duties)
