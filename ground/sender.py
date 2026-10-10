"""The sender thread: sends the newest Command every 20 ms, whatever the window is doing.

Two workers share one "mailbox":
    UI thread     -> publish(cmd)   every frame: "here's the latest command"
    sender thread -> every 1/rate s: take the newest command, number it, send it

If the UI freezes (window dragged), the sender keeps going with the last command.
If the UI freezes for too long (program hung), the sender deliberately goes quiet,
so the Pi's failsafe takes over. Every layer watches the one upstream of it.
"""

import dataclasses
import threading
import time

from common.ground_link import Command, encode

UI_STALE = 0.25   # UI silent longer than this -> centre the sticks, hold throttle
UI_DEAD = 1.0     # UI silent longer than this -> stop sending on purpose


def outgoing(cmd: Command | None, ui_age: float) -> Command | None:
    """What should go out, given the newest UI command and how old it is (seconds).

    Pure function (no threads, no clock) so the rules can be unit-tested directly.
    Returns None for "send nothing".
    """
    if cmd is None or ui_age > UI_DEAD:
        return None
    if ui_age > UI_STALE:
        # dataclasses.replace builds a NEW Command with some fields changed
        # (the original is frozen, so it can't be edited in place).
        return dataclasses.replace(cmd, roll=0.0, pitch=0.0, yaw=0.0)
    return cmd


def ui_state(cmd: Command | None, ui_age: float) -> str:
    """Human-readable label for the display."""
    if cmd is None:
        return "WAITING"
    if ui_age > UI_DEAD:
        return "UI DEAD: not sending"
    if ui_age > UI_STALE:
        return "UI STALE: sticks centred"
    return "OK"


class Sender:
    """Owns the sending side of the socket and the second thread."""

    def __init__(self, sock, address, rate: int = 50):
        self._sock = sock
        self._address = address
        self._period = 1.0 / rate

        # The mailbox. The lock is a "talking stick": only the holder may touch _cmd/_cmd_time,
        # so the sender can never read a new command paired with an old timestamp.
        self._lock = threading.Lock()
        self._cmd: Command | None = None
        self._cmd_time = 0.0

        # Statistics, written only by the sender thread; the UI just reads them for display.
        self.seq = 0
        self.sent = 0
        self.errors = 0
        self.last_error = ""
        self.state = "WAITING"
        self.send_gaps: list[float] = []

        self._running = False
        # daemon=True: if the main program dies, this thread dies with it (no zombie sender).
        self._thread = threading.Thread(target=self._run, name="sender", daemon=True)

    # ---- called from the UI thread ----
    def publish(self, cmd: Command) -> None:
        with self._lock:
            self._cmd = cmd
            self._cmd_time = time.perf_counter()

    def start(self) -> None:
        self._running = True
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=1.0)   # wait for the thread to finish its current loop

    # ---- runs in the sender thread ----
    def _run(self) -> None:
        next_t = time.perf_counter()
        last_send = None
        while self._running:
            with self._lock:
                cmd, t_ui = self._cmd, self._cmd_time
            now = time.perf_counter()
            ui_age = now - t_ui
            self.state = ui_state(cmd, ui_age)

            out = outgoing(cmd, ui_age)
            if out is not None:
                self.seq += 1          # seq is assigned HERE: one number per packet actually sent
                try:
                    self._sock.sendto(encode(dataclasses.replace(out, seq=self.seq)), self._address)
                    self.sent += 1
                    t = time.perf_counter()
                    if last_send is not None:
                        self.send_gaps.append(t - last_send)
                    last_send = t
                except OSError as e:
                    self.errors += 1
                    self.last_error = str(e)[:60]
            else:
                last_send = None       # a deliberate pause isn't a "gap" in the statistics

            # Schedule against an absolute timeline (next_t += period) instead of "sleep 20 ms":
            # small delays then don't accumulate into drift.
            next_t += self._period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()   # fell behind: carry on, don't fire a catch-up burst
