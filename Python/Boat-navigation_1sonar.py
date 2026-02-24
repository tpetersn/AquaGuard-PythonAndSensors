import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
import random
import math
import threading
import serial

# --- parameters ---
POOL_WIDTH      = 200   # cm (real-world scale — 1 unit = 1 cm)
POOL_HEIGHT     = 200
BOAT_SPEED      = 2     # cm per step
TURN_SPEED      = 10    # degrees per step
SENSOR_MAX_DIST = 195   # cm — cap slightly inside pool
COLLISION_DIST  = 30    # cm — reverse when object closer than this

# --- real sonar (JSNR04T-2.0, Trig=D7, Echo=D6) ---
SERIAL_PORT = "COM4"
BAUD_RATE   = 9600

_real_front_dist = SENSOR_MAX_DIST
_serial_lock     = threading.Lock()
_sonar_connected = False

def _serial_reader():
    global _real_front_dist, _sonar_connected
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        _sonar_connected = True
        print(f"[sonar] connected on {SERIAL_PORT}")
        while True:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if line.startswith("SONAR:"):
                try:
                    dist = float(line[6:])
                    with _serial_lock:
                        _real_front_dist = min(dist, SENSOR_MAX_DIST)
                except ValueError:
                    pass
    except Exception as e:
        print(f"[sonar] not available ({e}) — front sensor will use raycast")

threading.Thread(target=_serial_reader, daemon=True).start()


class State:
    CRUISE  = "CRUISE"
    REVERSE = "REVERSE"
    TURN    = "TURN"


class AquaguardSim:
    def __init__(self):
        self.x       = POOL_WIDTH / 2
        self.y       = POOL_HEIGHT / 2
        self.heading = random.uniform(0, 360)
        self.state   = State.CRUISE

        self.reverse_counter   = 0
        self.turn_target_angle = 0
        self.turn_accumulated  = 0

        self.front_dist = SENSOR_MAX_DIST
        # world-space position of the detected object (tip of the sonar ray)
        self.obj_x = self.x
        self.obj_y = self.y

    def _raycast_front(self):
        ray_angle = math.radians(self.heading)
        dist = SENSOR_MAX_DIST
        cos_a = math.cos(ray_angle)
        sin_a = math.sin(ray_angle)
        if cos_a > 0:   dist = min(dist, (POOL_WIDTH  - self.x) / cos_a)
        elif cos_a < 0: dist = min(dist, -self.x / cos_a)
        if sin_a > 0:   dist = min(dist, (POOL_HEIGHT - self.y) / sin_a)
        elif sin_a < 0: dist = min(dist, -self.y / sin_a)
        return dist

    def update(self):
        # --- read front sensor ---
        if _sonar_connected:
            with _serial_lock:
                self.front_dist = _real_front_dist
        else:
            self.front_dist = self._raycast_front()

        # --- compute detected object position in world space ---
        rad = math.radians(self.heading)
        self.obj_x = self.x + self.front_dist * math.cos(rad)
        self.obj_y = self.y + self.front_dist * math.sin(rad)

        # --- FSM ---
        if self.state == State.CRUISE:
            if self.front_dist < COLLISION_DIST:
                self.state           = State.REVERSE
                self.reverse_counter = 12
            else:
                self.x += math.cos(rad) * BOAT_SPEED
                self.y += math.sin(rad) * BOAT_SPEED

        elif self.state == State.REVERSE:
            if self.reverse_counter > 0:
                self.x -= math.cos(rad) * (BOAT_SPEED * 0.5)
                self.y -= math.sin(rad) * (BOAT_SPEED * 0.5)
                self.reverse_counter -= 1
            else:
                self.state            = State.TURN
                turn_dir              = random.choice([-1, 1])
                angle                 = random.randint(70, 130)
                self.turn_target_angle = angle * turn_dir
                self.turn_accumulated  = 0

        elif self.state == State.TURN:
            if abs(self.turn_accumulated) < abs(self.turn_target_angle):
                step = TURN_SPEED if self.turn_target_angle > 0 else -TURN_SPEED
                self.heading          += step
                self.turn_accumulated += step
            else:
                self.state = State.CRUISE

        self.x = max(20, min(POOL_WIDTH  - 20, self.x))
        self.y = max(20, min(POOL_HEIGHT - 20, self.y))


# --- visualization ---
fig, ax = plt.subplots(figsize=(14, 9))
sim = AquaguardSim()

ax.add_patch(plt.Rectangle((0, 0), POOL_WIDTH, POOL_HEIGHT,
                            fill=False, lw=3, color='black'))

# danger zone circle (fixed radius = COLLISION_DIST, centred on boat each frame)
danger_circle = mpatches.Circle((sim.x, sim.y), COLLISION_DIST / 2,
                                 color='red', fill=True, alpha=0.12,
                                 zorder=1, label=f'Danger zone ({COLLISION_DIST} cm)')

ax.add_patch(danger_circle)

boat_dot,   = ax.plot([], [], 'ro',  markersize=10, zorder=5, label='Boat')
boat_dir,   = ax.plot([], [], 'r-',  lw=2,          zorder=4)
ray_front,  = ax.plot([], [], 'g--', lw=1.5, alpha=0.7, zorder=3, label='Sonar ray')
# detected object marker — orange X when object is closer than SENSOR_MAX_DIST
obj_marker, = ax.plot([], [], 'X',   color='darkorange', markersize=14,
                      zorder=6, label='Detected object')
# line from boat directly to object (absolute position in box)
obj_line,   = ax.plot([], [], '-',   color='orange', lw=1, alpha=0.5, zorder=2)

status_text = ax.text(20, POOL_HEIGHT + 30, "", fontsize=11,
                      color='blue', fontfamily='monospace')

ax.set_xlim(-60, POOL_WIDTH + 60)
ax.set_ylim(-60, POOL_HEIGHT + 100)
ax.set_aspect('equal')
ax.set_title("Aquaguard — 1 sonar (front, REAL)  |  orange X = detected object position in pool")
ax.legend(loc='upper right', fontsize=9)
ax.grid(True, alpha=0.2)


def animate(frame):
    sim.update()

    rad = math.radians(sim.heading)

    # boat
    boat_dot.set_data([sim.x], [sim.y])
    boat_dir.set_data(
        [sim.x, sim.x + 15 * math.cos(rad)],
        [sim.y, sim.y + 15 * math.sin(rad)]
    )

    # sonar ray
    ray_front.set_data(
        [sim.x, sim.x + sim.front_dist * math.cos(rad)],
        [sim.y, sim.y + sim.front_dist * math.sin(rad)]
    )

    # detected object marker — only show when something real is in range
    if sim.front_dist < SENSOR_MAX_DIST:
        obj_marker.set_data([sim.obj_x], [sim.obj_y])
        obj_line.set_data([sim.x, sim.obj_x], [sim.y, sim.obj_y])
        obj_marker.set_visible(True)
        obj_line.set_visible(True)
    else:
        obj_marker.set_visible(False)
        obj_line.set_visible(False)

    # danger circle follows the boat
    danger_circle.center = (sim.x, sim.y)
    # colour red when inside danger zone, grey otherwise
    if sim.front_dist < COLLISION_DIST:
        danger_circle.set_facecolor('red')
        danger_circle.set_alpha(0.25)
    else:
        danger_circle.set_facecolor('red')
        danger_circle.set_alpha(0.10)

    src = "REAL" if _sonar_connected else "SIM"
    status_text.set_text(
        f"State: {sim.state}   |   Front [{src}]: {int(sim.front_dist)} cm   |"
        f"   Object @ ({int(sim.obj_x)}, {int(sim.obj_y)})"
    )

    return boat_dot, boat_dir, ray_front, obj_marker, obj_line, status_text

ani = animation.FuncAnimation(fig, animate, interval=40, blit=False,
                               cache_frame_data=False)
plt.show()
