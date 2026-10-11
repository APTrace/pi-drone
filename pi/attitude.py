"""Attitude controller: "where the pilot wants the drone to point" vs "where it points" -> corrections.

    sticks (SafeCommand) --+
                           +--> AttitudeController.update() --> (roll, pitch, yaw) corrections --> mixer
    IMU (Attitude) --------+

PLACEHOLDER (1c-2): passes the sticks straight through and ignores the IMU. That's enough to test
the plumbing end to end (keys on the PC -> motor duties on the Pi). Real version (step 4):
three PID loops, one per axis, each turning "error = wanted - measured" into a correction.

Plug shape (keep it when the real PIDs arrive):
    controller.update(safe, attitude, dt) -> (roll, pitch, yaw)
"""

from pi.fakes import Attitude
from pi.safety import SafeCommand


class PassThroughController:
    def update(self, safe: SafeCommand, attitude: Attitude, dt: float):
        return safe.roll, safe.pitch, safe.yaw
