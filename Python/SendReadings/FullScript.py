import asyncio
import cv2
import json
import requests
import serial
import time
import pigpio
from livekit import rtc

from SendReadings import post_reading

# =================================================================
# === CONFIGURATION CONSTANTS ===
# =================================================================

ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

# --- Arduino (SENSORS ONLY) ---
ARDUINO_PORT = "/dev/ttyUSB0"
BAUD = 9600

# --- Device metadata ---
DEVICE_ID = "68cc90c7ef0763dddf1a5e9d"
CHLORINE = 1.1
BATTERY_VOLTAGE = 3.7
BATTERY_PERCENTAGE = 85

# --- Motor GPIO (BCM) ---
L_FWD = 18
L_REV = 19
R_FWD = 12
R_REV = 13

MAX_PWM = 45
DEADZONE = 0.02

arduino = None

# =================================================================
# === GPIO / MOTOR SETUP ===
# =================================================================

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("❌ pigpio daemon not running")

for pin in [L_FWD, L_REV, R_FWD, R_REV]:
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.set_PWM_frequency(pin, 20000)
    pi.set_PWM_dutycycle(pin, 0)

def stop_all():
    for pin in [L_FWD, L_REV, R_FWD, R_REV]:
        pi.set_PWM_dutycycle(pin, 0)

def clamp(val, lo=-1.0, hi=1.0):
    return max(lo, min(hi, val))

def set_motor(fwd, rev, value):
    pwm = int(abs(value) * MAX_PWM)
    if value > 0:
        pi.set_PWM_dutycycle(rev, 0)
        pi.set_PWM_dutycycle(fwd, pwm)
    elif value < 0:
        pi.set_PWM_dutycycle(fwd, 0)
        pi.set_PWM_dutycycle(rev, pwm)
    else:
        pi.set_PWM_dutycycle(fwd, 0)
        pi.set_PWM_dutycycle(rev, 0)

def drive_diff(throttle, turn):
    if abs(throttle) < DEADZONE:
        throttle = 0.0
    if abs(turn) < DEADZONE:
        turn = 0.0

    left = clamp(throttle + turn)
    right = clamp(throttle - turn)

    set_motor(L_FWD, L_REV, left)
    set_motor(R_FWD, R_REV, right)

stop_all()

# =================================================================
# === ARDUINO SERIAL (SENSORS ONLY)
# =================================================================

def init_arduino():
    global arduino
    try:
        if arduino and arduino.is_open:
            return
        arduino = serial.Serial(ARDUINO_PORT, BAUD, timeout=1.0)
        time.sleep(2)
        arduino.reset_input_buffer()
        print("🔌 Arduino connected (sensors only)")
    except Exception as e:
        print("❌ Arduino connection failed:", e)
        arduino = None

# =================================================================
# === CAMERA STREAMER
# =================================================================

class CameraStream(rtc.VideoSource):
    def __init__(self, width=640, height=480):
        super().__init__(width, height)
        self.cap = cv2.VideoCapture(0)
        self.width = width
        self.height = height

    async def run(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                await asyncio.sleep(0.1)
                continue

            frame = cv2.resize(frame, (self.width, self.height))
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)

            video_frame = rtc.VideoFrame(
                width=self.width,
                height=self.height,
                data=yuv.tobytes(),
                type=rtc.VideoBufferType.I420,
            )
            self.capture_frame(video_frame)
            await asyncio.sleep(0.03)

# =================================================================
# === SENSOR READER TASK
# =================================================================

async def sensor_reader_task():
    global arduino

    print("📡 Sensor reader started")

    while True:

        # ---------- Ensure Arduino connection ----------
        if arduino is None or not arduino.is_open:
            print("🔄 Arduino not connected — attempting reconnect...")
            init_arduino()
            await asyncio.sleep(1)
            continue

        # ---------- Read one line ----------
        def read_line():
            try:
                raw = arduino.readline()
                if not raw:
                    return None
                decoded = raw.decode("utf-8", errors="ignore").strip()
                return decoded
            except Exception as e:
                print("❌ Serial read exception:", repr(e))
                return None

        line = await asyncio.to_thread(read_line)

        if not line:
            await asyncio.sleep(0.05)
            continue

        print(f"🧾 RAW SERIAL: {line}")

        # ---------- Only process DATA lines ----------
        if not line.startswith("DATA:"):
            print("💬 Non-DATA line ignored")
            continue

        try:
            # ---------- Parse ----------
            payload = line.split("DATA:", 1)[1]
            parts = payload.split(",")

            data = {}
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    data[k.strip()] = v.strip()

            print("🔍 Parsed fields:", data)

            temperature = float(data.get("T1")) if data.get("T1") else None
            ph = float(data.get("pH")) if data.get("pH") else None
            tds = float(data.get("TDS")) if data.get("TDS") else None
            pitch = float(data.get("Pitch")) if data.get("Pitch") else None
            roll = float(data.get("Roll")) if data.get("Roll") else None

            print(
                f"📊 VALUES → Temp={temperature} pH={ph} TDS={tds} "
                f"Pitch={pitch} Roll={roll}"
            )

            # ---------- Post to backend ----------
            print("🌐 Posting to database...")

            response = post_reading(
                DEVICE_ID,
                temperature=temperature,
                ph=ph,
                chlorine=CHLORINE,
                tds=tds,
                battery_voltage=BATTERY_VOLTAGE,
                battery_percentage=BATTERY_PERCENTAGE,
                pitch=pitch,
                roll=roll,
            )

            # ---------- Response debug ----------
            if response is None:
                print("⚠️ post_reading() returned None")

            else:
                print("✅ POST SENT")
                print("   Status:", getattr(response, "status_code", "NO STATUS"))

                try:
                    print("   Response body:", response.text[:300])
                except:
                    print("   (No readable response body)")

        except Exception as e:
            print("❌ PROCESSING ERROR:")
            print("   Line:", line)
            print("   Error:", repr(e))

        await asyncio.sleep(0.05)


# =================================================================
# === MAIN ASYNC LOGIC
# =================================================================

async def main():
    init_arduino()
    asyncio.create_task(sensor_reader_task())

    token = requests.get(TOKEN_URL).json()["token"]
    room = rtc.Room()

    room.on("connected", lambda: print("✅ Connected to LiveKit"))
    room.on("disconnected", lambda: (print("❌ Disconnected"), stop_all()))

    @room.on("data_received")
    def on_data(packet):
        try:
            payload = json.loads(packet.data.decode())
            cmd = payload.get("cmd")

            if cmd == "set_direction":
                y = float(payload.get("y", 0.0))
                x = float(payload.get("x", 0.0))
                drive_diff(y, x)

            elif cmd == "set_speed":
                global MAX_PWM
                val = int(payload.get("value", 50))
                MAX_PWM = int(val / 100 * 255)
                
            elif cmd == "stop":
                drive_diff(0, 0)

            
            else:
                print("⚠️ Unknown command:", cmd)

        except Exception as e:
            print("❌ LiveKit command error:", e)

    await room.connect(ROOM_URL, token)

    camera = CameraStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    await room.local_participant.publish_track(track)

    print("📷 Video stream started")
    await camera.run()

# =================================================================
# === ENTRY
# =================================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        stop_all()
        pi.stop()
