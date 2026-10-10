"""Packet format for the ground station -> Pi command link (UDP).

Every packet carries the FULL command state (not key events), sent ~50x per second.
If one packet is lost, the next one simply replaces it.

Layout (26 bytes, little-endian):
    magic    2s   b"DR"            -> reject stray packets that aren't ours
    version  B    uint8            -> reject packets from an old/new format
    flags    B    uint8            -> bit0 = arm requested, bit1 = kill
    session  H    uint16           -> random per ground-station run
    seq      I    uint32           -> +1 per packet
    throttle f    float32  0..1
    roll     f    float32 -1..1
    pitch    f    float32 -1..1
    yaw      f    float32 -1..1
"""

import math
import struct
from dataclasses import dataclass

MAGIC = b"DR"
VERSION = 1

FLAG_ARM = 0b01
FLAG_KILL = 0b10
_KNOWN_FLAGS = FLAG_ARM | FLAG_KILL

# "<" = little-endian, no padding. Compiled once, reused for every packet.
_FORMAT = struct.Struct("<2sBBHI4f")
PACKET_SIZE = _FORMAT.size  # 26


@dataclass(frozen=True)
class Command:
    """One snapshot of what the pilot is asking for.

    frozen=True: a Command can't be modified after creation, so nothing
    downstream can accidentally change a command it was handed.
    """
    throttle: float = 0.0   # 0..1
    roll: float = 0.0       # -1..1
    pitch: float = 0.0      # -1..1
    yaw: float = 0.0        # -1..1
    arm: bool = False       # arm REQUESTED -- the Pi decides whether to grant it
    kill: bool = False
    session: int = 0
    seq: int = 0


def encode(cmd: Command) -> bytes:
    """Command -> 26 bytes. Used by the ground station."""
    flags = (FLAG_ARM if cmd.arm else 0) | (FLAG_KILL if cmd.kill else 0)
    return _FORMAT.pack(
        MAGIC, VERSION, flags,
        cmd.session & 0xFFFF,        # keep within uint16
        cmd.seq & 0xFFFFFFFF,        # keep within uint32 (wraps after ~2.7 years at 50 Hz)
        cmd.throttle, cmd.roll, cmd.pitch, cmd.yaw,
    )


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def decode(data: bytes) -> Command | None:
    """26 bytes -> Command, or None if the packet is invalid. Used by the Pi.

    The Pi trusts nothing: anything malformed is dropped (None), and values
    are clamped to their legal range.
    """
    if len(data) != PACKET_SIZE:
        return None
    magic, version, flags, session, seq, t, r, p, y = _FORMAT.unpack(data)
    if magic != MAGIC or version != VERSION:
        return None
    if flags & ~_KNOWN_FLAGS:
        return None
    # NaN/inf must be rejected BEFORE clamping: min(1.0, nan) returns 1.0,
    # so a NaN throttle would silently become FULL throttle.
    if not all(math.isfinite(v) for v in (t, r, p, y)):
        return None
    return Command(
        throttle=_clamp(t, 0.0, 1.0),
        roll=_clamp(r, -1.0, 1.0),
        pitch=_clamp(p, -1.0, 1.0),
        yaw=_clamp(y, -1.0, 1.0),
        arm=bool(flags & FLAG_ARM),
        kill=bool(flags & FLAG_KILL),
        session=session,
        seq=seq,
    )
