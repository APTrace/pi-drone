"""CommandReceiver: owns the UDP socket and answers one question: "what's the newest command,
and how old is it?"

The crucial difference from tools/udp_peek.py: this socket is NON-BLOCKING.
    blocking     recvfrom(): "wait here until a packet arrives"  (could wait forever!)
    non-blocking recvfrom(): "give me a packet if one is waiting, otherwise say so IMMEDIATELY"
The control loop calls poll() every iteration and must never be held hostage by the network.
"""

import math
import socket
import time

from common.ground_link import DEFAULT_PORT, Command, decode


class CommandReceiver:
    def __init__(self, port: int = DEFAULT_PORT, host: str = "0.0.0.0"):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, port))
        self._sock.setblocking(False)          # <- the whole point

        self._latest: Command | None = None
        self._arrival = 0.0                    # time.monotonic() when _latest arrived

        # Counters, for the display and for debugging.
        self.accepted = 0
        self.rejected = 0       # failed decode(): wrong size / magic / version / NaN ...
        self.out_of_order = 0   # valid, but older than what we already have (UDP reordering)

    def poll(self) -> None:
        """Drain EVERYTHING waiting in the socket, keep only the newest valid command.

        If the loop hiccuped and 3 packets piled up, we jump straight to the newest one
        instead of replaying stale commands. Takes microseconds when nothing is waiting.
        """
        while True:
            try:
                data, _addr = self._sock.recvfrom(64)
            except BlockingIOError:            # "nothing waiting": done for this iteration
                return
            cmd = decode(data)
            if cmd is None:
                self.rejected += 1
                continue
            prev = self._latest
            if prev is not None and cmd.session == prev.session and cmd.seq <= prev.seq:
                self.out_of_order += 1         # arrived late, we already have something newer
                continue
            # A different session is always accepted: it's a restarted ground station
            # (the SafetyManager then forces a disarm).
            self._latest = cmd
            self._arrival = time.monotonic()
            self.accepted += 1

    def latest(self) -> tuple[Command | None, float]:
        """(newest command, its age in seconds). Age is infinite if nothing ever arrived."""
        if self._latest is None:
            return None, math.inf
        return self._latest, time.monotonic() - self._arrival

    def close(self) -> None:
        self._sock.close()
