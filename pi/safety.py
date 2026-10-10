"""SafetyManager: turns "what the pilot asked for" into "what the drone is allowed to do".

Pure logic: no sockets, and no clock of its own. The caller passes in the link age and the
current time. That makes every rule testable with fake times (a 3 s landing tested in µs).

States:
    DISARMED -> ARMED -> LEVEL -> DESCEND -> DISARMED
                  ^________|
    ARMED:   normal flight, pilot's command passed through
    LEVEL:   link silent > LEVEL_AFTER: sticks centred, throttle held; recovers when packets return
    DESCEND: link silent > DESCEND_AFTER: throttle ramps to 0 over DESCENT_TIME, then disarm.
             One-way door: continues even if the link comes back.
    KILL:    instant disarm from any state.

Re-arming after any FORCED disarm (kill, landing, new session, boot) needs the arm request to be
released first (arm flag seen False), then requested again at zero throttle.
"""

from dataclasses import dataclass

from common.ground_link import Command

LEVEL_AFTER = 0.25     # s of link silence before levelling out
DESCEND_AFTER = 1.0    # s of link silence before starting a controlled descent
DESCENT_TIME = 2.0     # s to ramp throttle from its last value down to 0


@dataclass(frozen=True)
class SafeCommand:
    """What the rest of the drone (mixer, motors) is allowed to act on. Small and boring on purpose."""
    throttle: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    armed: bool = False


OFF = SafeCommand()   # motors off, disarmed


class SafetyManager:
    def __init__(self):
        self.state = "DISARMED"
        self.armed = False
        self._arm_released = False     # must see arm=False before arming (also at boot)
        self._session = None
        self._last_throttle = 0.0      # throttle we last allowed (start point for a descent)
        self._descent_start = 0.0
        self.events: list[str] = []    # human-readable log of state changes, for the display

    def pop_events(self) -> list[str]:
        """Return and clear the state-change messages (the monitor prints them)."""
        out, self.events = self.events, []
        return out

    # ---------------------------------------------------------------- helpers
    def _event(self, text: str) -> None:
        self.events.append(text)

    def _force_disarm(self, reason: str) -> None:
        if self.armed:
            self._event(f"DISARMED: {reason}")
        self.armed = False
        self._arm_released = False     # forced disarm: pilot must release + re-request arm
        self.state = "DISARMED"

    # ---------------------------------------------------------------- main entry point
    def update(self, cmd: Command | None, age: float, now: float) -> SafeCommand:
        """Call once per loop iteration.

        cmd: newest valid command (None if nothing ever arrived)
        age: seconds since that command arrived
        now: current time (monotonic seconds), only used to time the descent ramp
        """
        if cmd is None:
            self.state = "NO LINK"
            return OFF

        # Rule 5: a new ground-station session never inherits an armed drone.
        if self._session is not None and cmd.session != self._session:
            self._force_disarm("new ground-station session")
        self._session = cmd.session

        # Rule 3: KILL beats everything, every time.
        if cmd.kill:
            if self.armed:
                self._event("KILL")
            self._force_disarm("KILL")
            if not cmd.arm:
                self._arm_released = True  # ground station clears arm on kill: that IS the release
            return OFF

        # A descent in progress continues no matter what the link does (one-way door).
        if self.state == "DESCEND":
            return self._descend(now)

        # Normal disarm request (Q): arm flag off -> disarm, and it counts as "released".
        if not cmd.arm:
            if self.armed:
                self._event("DISARMED: pilot request")
            self.armed = False
            self.state = "DISARMED"
            self._arm_released = True

        # Rule 2: arming needs a released-then-requested arm, zero throttle, and a FRESH link.
        if not self.armed:
            if cmd.arm and self._arm_released and age <= LEVEL_AFTER:
                if cmd.throttle == 0.0:
                    self.armed = True
                    self._arm_released = False
                    self.state = "ARMED"
                    self._event("ARMED")
                else:
                    self.state = "DISARMED (throttle not 0)"
            elif age > LEVEL_AFTER:
                self.state = "DISARMED (link lost)"
            return OFF

        # Armed: Rule 1, the staged failsafe, chosen by how old the newest command is.
        if age <= LEVEL_AFTER:
            if self.state != "ARMED":
                self._event("link back: ARMED")
            self.state = "ARMED"
            out = SafeCommand(cmd.throttle, cmd.roll, cmd.pitch, cmd.yaw, armed=True)
        elif age <= DESCEND_AFTER:
            if self.state != "LEVEL":
                self._event(f"LEVEL: link silent {age:.2f} s")
            self.state = "LEVEL"
            out = SafeCommand(cmd.throttle, 0.0, 0.0, 0.0, armed=True)
        else:
            self._event(f"DESCEND: link silent {age:.2f} s")
            self.state = "DESCEND"
            self._descent_start = now
            return self._descend(now)

        self._last_throttle = out.throttle
        return out

    def _descend(self, now: float) -> SafeCommand:
        """Linear throttle ramp from the last allowed throttle to 0, then disarm."""
        progress = (now - self._descent_start) / DESCENT_TIME     # 0 at start, 1 when done
        if progress >= 1.0:
            self._force_disarm("failsafe landing complete")
            return OFF
        return SafeCommand(self._last_throttle * (1.0 - progress), 0.0, 0.0, 0.0, armed=True)
