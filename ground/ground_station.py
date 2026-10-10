"""Ground station: keyboard -> Command -> 26-byte UDP packet -> Pi, 50 times per second.

Two threads: this file is the UI thread (window, keys, drawing); ground/sender.py is the
sender thread, which keeps sending even while the window is frozen (e.g. being dragged).

Run from the repo root (with the venv active):
    python -m ground.ground_station                     # sends to drone.local
    python -m ground.ground_station --host 192.168.1.24 # if the name doesn't resolve

Keys (only while this window has focus):
    W / S     throttle up / down (stays where you leave it)
    arrows    pitch / roll (snap back to 0 on release)
    A / D     yaw          (snap back to 0 on release)
    E / Q     request arm / disarm
    SPACE     KILL
    ESC       quit
"""

import argparse
import random
import socket

import pygame

from common.gapstats import summarize
from common.ground_link import DEFAULT_PORT
from ground.controls import Controls, Inputs
from ground.sender import Sender

STICK = 0.3   # stick deflection while an arrow / A / D is held (gentle on purpose)

# Colours (R, G, B)
BG = (24, 26, 30)
FG = (220, 220, 220)
DIM = (120, 120, 120)
GREEN = (80, 200, 120)
RED = (230, 70, 70)
AMBER = (240, 180, 60)
BAR_BG = (55, 58, 64)


def read_keyboard() -> Inputs:
    """The ONLY function that knows about the keyboard. A gamepad version would return the same Inputs."""
    k = pygame.key.get_pressed()   # which keys are held RIGHT NOW (all False if window unfocused)
    return Inputs(
        throttle_dir=int(k[pygame.K_w]) - int(k[pygame.K_s]),
        roll=STICK * (int(k[pygame.K_RIGHT]) - int(k[pygame.K_LEFT])),
        pitch=STICK * (int(k[pygame.K_UP]) - int(k[pygame.K_DOWN])),
        yaw=STICK * (int(k[pygame.K_d]) - int(k[pygame.K_a])),
        arm=bool(k[pygame.K_e]),
        disarm=bool(k[pygame.K_q]),
        kill=bool(k[pygame.K_SPACE]),
    )


def draw_bar(screen, font, x, y, label, value, lo, hi):
    """Horizontal bar. For centred sticks (lo=-1) the fill grows from the middle."""
    w, h = 300, 22
    pygame.draw.rect(screen, BAR_BG, (x, y, w, h), border_radius=4)
    if lo < 0:
        mid = x + w // 2
        end = mid + int(value / hi * w / 2)
        pygame.draw.rect(screen, AMBER, (min(mid, end), y, abs(end - mid), h), border_radius=4)
        pygame.draw.line(screen, DIM, (mid, y), (mid, y + h))
    else:
        pygame.draw.rect(screen, GREEN, (x, y, int(value / hi * w), h), border_radius=4)
    screen.blit(font.render(label, True, FG), (x - 95, y + 2))
    screen.blit(font.render(f"{value:+.2f}", True, FG), (x + w + 10, y + 2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Pi drone ground station")
    ap.add_argument("--host", default="drone.local", help="Pi hostname or IP (default: drone.local)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--rate", type=int, default=50, help="packets per second (default: 50)")
    args = ap.parse_args()

    # Resolve the name ONCE, at start-up. Name lookup can take a while; doing it inside
    # the 50 Hz loop would make every packet wait for it.
    try:
        ip = socket.gethostbyname(args.host)
    except socket.gaierror:
        print(f"Can't find '{args.host}'. Is the Pi on? Try --host 192.168.1.24 (its IP).")
        return
    print(f"Sending to {args.host} = {ip}:{args.port} at {args.rate} Hz. Close the window or ESC to quit.")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # DGRAM = UDP
    session = random.randint(1, 0xFFFF)                      # new number every run (see ground_link.py)
    controls = Controls(session)

    pygame.init()
    screen = pygame.display.set_mode((560, 330))
    pygame.display.set_caption("Pi drone - ground station")
    font = pygame.font.SysFont("consolas", 18)
    big = pygame.font.SysFont("consolas", 30, bold=True)
    clock = pygame.time.Clock()

    sender = Sender(sock, (ip, args.port), rate=args.rate)
    sender.start()                                # worker B starts sending in the background

    running = True
    while running:
        # The UI only needs to keep up with human eyes and fingers; 50 fps is plenty.
        dt = clock.tick(50) / 1000.0

        for event in pygame.event.get():          # must be drained every frame or Windows says "Not responding"
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # 1. input -> 2. state -> 3. hand to the sender. The UI never touches the network itself.
        cmd = controls.update(read_keyboard(), dt)
        sender.publish(cmd)

        # --- display ---
        screen.fill(BG)
        if cmd.kill:
            status, colour = "KILL", RED
        elif cmd.arm:
            status, colour = "ARM REQUESTED", GREEN
        else:
            status, colour = "DISARMED", DIM
        screen.blit(big.render(status, True, colour), (20, 15))
        if not pygame.key.get_focused():
            screen.blit(font.render("window not focused: keys ignored", True, AMBER), (270, 25))

        draw_bar(screen, font, 115, 70, "throttle", cmd.throttle, 0, 1)
        draw_bar(screen, font, 115, 102, "roll", cmd.roll, -1, 1)
        draw_bar(screen, font, 115, 134, "pitch", cmd.pitch, -1, 1)
        draw_bar(screen, font, 115, 166, "yaw", cmd.yaw, -1, 1)

        screen.blit(font.render(controls.message, True, FG), (20, 210))
        info = f"to {ip}:{args.port}  session {session}  seq {sender.seq}  sender: {sender.state}"
        screen.blit(font.render(info, True, DIM), (20, 245))
        err_txt = f"send errors: {sender.errors}" + (f"  ({sender.last_error})" if sender.errors else "")
        screen.blit(font.render(err_txt, True, RED if sender.errors else DIM), (20, 270))
        screen.blit(font.render("W/S thr  arrows  A/D yaw  E arm  Q disarm  SPACE kill", True, DIM), (20, 300))
        pygame.display.flip()

    # No "goodbye" packet on purpose: stopping = silence, and the Pi's failsafe must handle silence.
    sender.stop()
    pygame.quit()
    print(f"Stopped. Sent {sender.sent} packets, {sender.errors} send errors.")
    summarize(sender.send_gaps, "Sends from PC")


if __name__ == "__main__":
    main()
