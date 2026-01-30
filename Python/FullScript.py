import asyncio
import json
import requests
import pigpio
from livekit import rtc

# =====================================================
# CONFIG
# =====================================================

ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

# LEFT motor
L_FWD = 18
L_REV = 19

# RIGHT motor
R_FWD = 12
R_REV = 13

MAX_PWM = 180
DEADZONE = 0.02

# =====================================================
# GPIO INIT
# =====================================================

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running")

for pin in [L_FWD, L_REV, R_FWD, R_REV]:
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.set_PWM_frequency(pin, 20000)
    pi.set_PWM_dutycycle(pin, 0)

def stop_all():
    for pin in [L_FWD, L_REV, R_FWD, R_REV]:
        pi.set_PWM_dutycycle(pin, 0)

stop_all()

# =====================================================
# MOTOR HELPERS
# =====================================================

def clamp(val, lo=-1.0, hi=1.0):
    return max(lo, min(hi, val))

def set_motor(fwd_pin, rev_pin, value):
    """value: -1.0 .. +1.0"""
    pwm = int(abs(value) * MAX_PWM)

    if value > 0:
        pi.set_PWM_dutycycle(rev_pin, 0)
        pi.set_PWM_dutycycle(fwd_pin, pwm)
    elif value < 0:
        pi.set_PWM_dutycycle(fwd_pin, 0)
        pi.set_PWM_dutycycle(rev_pin, pwm)
    else:
        pi.set_PWM_dutycycle(fwd_pin, 0)
        pi.set_PWM_dutycycle(rev_pin, 0)

def drive_diff(throttle, turn):
    if abs(throttle) < DEADZONE:
        throttle = 0.0
    if abs(turn) < DEADZONE:
        turn = 0.0

    left  = clamp(throttle + turn)
    right = clamp(throttle - turn)

    set_motor(L_FWD, L_REV, left)
    set_motor(R_FWD, R_REV, right)

# =====================================================
# LIVEKIT
# =====================================================

async def main():
    token = requests.get(TOKEN_URL).json()["token"]
    room = rtc.Room()

    @room.on("connected")
    def _():
        print("✅ Connected")

    @room.on("disconnected")
    def _():
        print("❌ Disconnected")
        stop_all()

    @room.on("data_received")
    def on_data(packet):
        try:
            payload = json.loads(packet.data.decode())
            cmd = payload.get("cmd")

            if cmd == "set_direction":
                y = float(payload.get("y", 0.0))  # throttle
                x = float(payload.get("x", 0.0))  # turn
                drive_diff(y, x)

            elif cmd == "set_speed":
                global MAX_PWM
                val = int(payload.get("value", 50))
                MAX_PWM = int(val / 100 * 255)

        except Exception as e:
            print("Command error:", e)

    await room.connect(ROOM_URL, token)

    # Camera
    camera = CameraStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    await room.local_participant.publish_track(track)

    print("📷 Video stream started")
    while True:
        await asyncio.sleep(1)

# =====================================================
# ENTRY
# =====================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        stop_all()
        pi.stop()
