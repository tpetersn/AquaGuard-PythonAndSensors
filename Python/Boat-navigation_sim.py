import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import random
import math

# --- parameters ---
POOL_WIDTH = 1000   
POOL_HEIGHT = 500   
BOAT_SPEED = 20     
TURN_SPEED = 10     
SENSOR_MAX_DIST = 200 
COLLISION_DIST = 60  #   threshold distance to decide front sonar collision
DEAD_CORNER_DIST = 50 # threshold distance to decide dead corner on left and right sides sonars

class State:
    CRUISE = "CRUISE"
    REVERSE = "REVERSE"
    TURN = "TURN"

class AquaguardSim:
    def __init__(self):
        self.x = POOL_WIDTH / 2
        self.y = POOL_HEIGHT / 2
        self.heading = random.uniform(0, 360) 
        self.state = State.CRUISE
        
        self.reverse_counter = 0
        self.turn_target_angle = 0
        self.turn_accumulated = 0
        
        # memory for collision type
        self.collision_type = "NONE" # record the type of collision
        
        self.sensors = {'front': 0, 'left': 0, 'right': 0}

    def raycast(self, angle_offset):
        ray_angle = math.radians(self.heading + angle_offset)
        dist = SENSOR_MAX_DIST
        sin_a = math.sin(ray_angle)
        cos_a = math.cos(ray_angle)
        
        if cos_a > 0: d = (POOL_WIDTH - self.x) / cos_a
        elif cos_a < 0: d = -self.x / cos_a
        else: d = SENSOR_MAX_DIST
        if d > 0: dist = min(dist, d)
            
        if sin_a > 0: d = (POOL_HEIGHT - self.y) / sin_a
        elif sin_a < 0: d = -self.y / sin_a
        else: d = SENSOR_MAX_DIST
        if d > 0: dist = min(dist, d)
        return dist

    def update(self):
        # 1. update sensors
        self.sensors['front'] = self.raycast(0)
        self.sensors['left'] = self.raycast(90)
        self.sensors['right'] = self.raycast(-90)
        
        # 2. finite state machine
        if self.state == State.CRUISE:
            if self.sensors['front'] < COLLISION_DIST:
                self.state = State.REVERSE
                self.reverse_counter = 12 
                
                # --- snapshot on deadcorner condtion with AND ---
                
                # get left and right sonar status
                left_blocked = self.sensors['left'] < DEAD_CORNER_DIST
                right_blocked = self.sensors['right'] < DEAD_CORNER_DIST
                
                # case A: True dead corner(both sides collide) -> AND
                if left_blocked and right_blocked:
                    self.collision_type = "TRAPPED"
                    
                # case B: single side hit wall  -> record which side
                elif left_blocked:
                    self.collision_type = "LEFT_BLOCKED"
                elif right_blocked:
                    self.collision_type = "RIGHT_BLOCKED"
                    
                # case C: collision on front only -> both sides free
                else:
                    self.collision_type = "FREE"

            else:
                rad = math.radians(self.heading)
                self.x += math.cos(rad) * BOAT_SPEED
                self.y += math.sin(rad) * BOAT_SPEED

        elif self.state == State.REVERSE:
            if self.reverse_counter > 0:
                rad = math.radians(self.heading)
                self.x -= math.cos(rad) * (BOAT_SPEED * 0.5) 
                self.y -= math.sin(rad) * (BOAT_SPEED * 0.5)
                self.reverse_counter -= 1
            else:
                self.state = State.TURN
                
                # --- decision ---
                if self.collision_type == "TRAPPED":
                    # dead corner escape: turn 170 degrees away from closer wall
                    if self.sensors['left'] < self.sensors['right']:
                        self.turn_target_angle = 170 # right side has more space
                    else:
                        self.turn_target_angle = -170 # left side has more space
                        
                elif self.collision_type == "LEFT_BLOCKED":
                    # left side has wall, force turn right
                    # random angle between 70~100 (70% prob) or 110~150 (30% prob)
                    angle = random.randint(70, 100) if random.random() < 0.7 else random.randint(110, 150)
                    self.turn_target_angle = -angle # postive angle = right turn
                    
                elif self.collision_type == "RIGHT_BLOCKED":
                    # right side has wall, force turn left
                    angle = random.randint(70, 100) if random.random() < 0.7 else random.randint(110, 150)
                    self.turn_target_angle = angle # negative angle = left turn
                    
                else: # FREE
                    # choose random turn direction, if only front sonar collides
                    turn_dir = random.choice([-1, 1]) 
                    angle = random.randint(70, 100) if random.random() < 0.7 else random.randint(110, 150)
                    self.turn_target_angle = angle * turn_dir
                
                self.turn_accumulated = 0

        elif self.state == State.TURN:
            if abs(self.turn_accumulated) < abs(self.turn_target_angle):
                step = TURN_SPEED if self.turn_target_angle > 0 else -TURN_SPEED
                self.heading += step
                self.turn_accumulated += step
            else:
                self.state = State.CRUISE

        self.x = max(20, min(POOL_WIDTH - 20, self.x))
        self.y = max(20, min(POOL_HEIGHT - 20, self.y))

# --- visulization ---
fig, ax = plt.subplots(figsize=(10, 6))
sim = AquaguardSim()

pool_rect = plt.Rectangle((0, 0), POOL_WIDTH, POOL_HEIGHT, fill=False, lw=3, color='black')
ax.add_patch(pool_rect)

boat_dot, = ax.plot([], [], 'ro', markersize=10, label='Robot') 
boat_dir, = ax.plot([], [], 'r-', lw=2) 
ray_front, = ax.plot([], [], 'g--', alpha=0.5)
ray_left, = ax.plot([], [], 'g--', alpha=0.5)
ray_right, = ax.plot([], [], 'g--', alpha=0.5)
limit_left, = ax.plot([], [], 'r-', lw=3, alpha=0.6)
limit_right, = ax.plot([], [], 'r-', lw=3, alpha=0.6)

status_text = ax.text(20, POOL_HEIGHT + 20, "", fontsize=12, color='blue', fontfamily='monospace')

ax.set_xlim(-50, POOL_WIDTH + 50)
ax.set_ylim(-50, POOL_HEIGHT + 50)
ax.set_aspect('equal')
ax.set_title("Aquaguard: Dead Corner Escape + Smart Turn")
ax.grid(True, alpha=0.3)

def animate(frame):
    sim.update()
    boat_dot.set_data([sim.x], [sim.y])
    rad = math.radians(sim.heading)
    boat_dir.set_data([sim.x, sim.x + 60 * math.cos(rad)], 
                      [sim.y, sim.y + 60 * math.sin(rad)])
    
    def get_ray_coords(dist, angle_offset):
        r_angle = math.radians(sim.heading + angle_offset)
        return ([sim.x, sim.x + dist * math.cos(r_angle)],
                [sim.y, sim.y + dist * math.sin(r_angle)])

    fx, fy = get_ray_coords(sim.sensors['front'], 0)
    ray_front.set_data(fx, fy)
    lx, ly = get_ray_coords(sim.sensors['left'], 90)
    ray_left.set_data(lx, ly)
    rx, ry = get_ray_coords(sim.sensors['right'], -90)
    ray_right.set_data(rx, ry)

    lx_lim, ly_lim = get_ray_coords(DEAD_CORNER_DIST, 90)
    limit_left.set_data(lx_lim, ly_lim)
    rx_lim, ry_lim = get_ray_coords(DEAD_CORNER_DIST, -90)
    limit_right.set_data(rx_lim, ry_lim)
    
    status_msg = (
        f"State: {sim.state}\n" #display current state
        f"Type: {sim.collision_type}\n" # display collision type
        f"Front: {int(sim.sensors['front'])}" #display front sonar distance
        f" | Left: {int(sim.sensors['left'])}" #display left sonar distance
        f" | Right: {int(sim.sensors['right'])}" #display right sonar distance
    )
    status_text.set_text(status_msg)
    return boat_dot, boat_dir, ray_front, ray_left, ray_right, limit_left, limit_right, status_text

ani = animation.FuncAnimation(fig, animate, frames=200, interval=40, blit=True)
plt.show()