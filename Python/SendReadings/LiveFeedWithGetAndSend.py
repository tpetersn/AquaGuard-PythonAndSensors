import asyncio
import cv2
import json
import requests
import serial
import time
from livekit import rtc

from SendReadings import post_reading

# =================================================================
# === CONFIGURATION CONSTANTS ===
# =================================================================

ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

ARDUINO_PORT = "/dev/ttyUSB0"   # Adjust if needed
BAUD         = 9600

DEVICE_ID = "68cc90c7ef0763dddf1a5e9d"

CHLORINE           = 1.1
BATTERY_VOLTAGE    = 3.7
BATTERY_PERCENTAGE = 85

arduino = None


# =================================================================
# === ARDUINO SERIAL HELPERS ===
# =================================================================

def init_arduino():
    """Try to (re)connect to the Arduino."""
    global arduino
    try:
        if arduino and arduino.is_open:
            return

        arduino = serial.Serial(
            ARDUINO_PORT,
            BAUD,
            timeout=1.0,   # allow blocking read, avoid busy loop
        )
        time.sleep(2)  # wait for auto-reset
        arduino.reset_input_buffer()
        print(f"🔌 Arduino connected on {ARDUINO_PORT} @ {BAUD} baud")
    except Exception as e:
        print(f"❌ Could not connect to Arduino on {ARDUINO_PORT}: {e}")
        arduino = None


def send_cmd(cmd: str):
    """Send a command line to the Arduino."""
    global arduino
    if arduino and arduino.is_open:
        try:
            arduino.write((cmd + "\n").encode("utf-8"))
        except Exception as e:
            print(f"❌ Failed to send '{cmd}' to Arduino: {e}")
    else:
        print("⚠️ Arduino not connected; command skipped:", cmd)


# =================================================================
# === CAMERA STREAMER ===
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
            frame_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)

            video_frame = rtc.VideoFrame(
                width=self.width,
                height=self.height,
                data=frame_yuv.tobytes(),
                type=rtc.VideoBufferType.I420,
            )

            self.capture_frame(video_frame)
            await asyncio.sleep(0.03)  # ~33 FPS


# =================================================================
# === SENSOR READER TASK ===
# =================================================================

async def sensor_reader_task():
    """
    Reads lines from Arduino, parses DATA packets, and posts readings.
    Runs forever as a background task.
    """
    global arduino

    print("📡 Sensor reader task started")

    while True:
        # Ensure Arduino is connected
        if arduino is None or not arduino.is_open:
            init_arduino()
            await asyncio.sleep(1.0)
            continue

        def read_one_line():
            """Blocking read of one line from Arduino (run in thread)."""
            try:
                line_bytes = arduino.readline()
            except Exception as e:
                print(f"❌ Error reading from Arduino: {e}")
                return None

            if not line_bytes:
                return None

            try:
                return line_bytes.decode("utf-8", errors="ignore").strip()
            except Exception as e:
                print(f"❌ Error decoding Arduino line: {e}")
                return None

        # Run blocking serial read in a thread
        line = await asyncio.to_thread(read_one_line)

        if not line:
            # No data this cycle
            await asyncio.sleep(0.1)
            continue

        # Debug if you want:
        # print("🔎 Raw line:", repr(line))

        if not line.startswith("DATA:"):
            # Other diagnostic messages from Arduino (if any)
            # print("💬 Arduino:", line)
            continue

        try:
            # Strip "DATA:" and parse key=value pairs
            payload = line.split("DATA:", 1)[1]
            parts = payload.split(",")

            data = {}
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    data[k.strip()] = v.strip()

            # Expected: T1, T2, TDS, pH, Pitch, Roll, Orient
            t1_str  = data.get("T1", "ERR")
            t2_str  = data.get("T2", "ERR")  # unused but available
            tds_str = data.get("TDS", "0")
            ph_str  = data.get("pH", "7.0")
            pitch_str = data.get("Pitch")
            roll_str  = data.get("Roll")
            orient    = data.get("Orient", "Unknown")

            temperature = float(t1_str) if t1_str not in (None, "ERR", "") else None
            tds         = float(tds_str)
            ph          = float(ph_str)

            pitch = float(pitch_str) if pitch_str not in (None, "ERR", "") else None
            roll  = float(roll_str)  if roll_str  not in (None, "ERR", "") else None

            print(
                f"🌡️ T1={temperature}°C  pH={ph:.2f}  TDS={tds:.0f}  "
                f"Pitch={pitch}° Roll={roll}°  Orient={orient}"
            )

            # Post reading to backend
            try:
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
                # Optional:
                # print("✅ Reading posted; status:", getattr(response, "status_code", "OK"))
            except Exception as e:
                print(f"❌ Error posting reading: {e}")

        except Exception as e:
            print(f"❌ Error processing DATA line '{line}': {e}")

        await asyncio.sleep(0.05)


# =================================================================
# === MAIN ASYNC LOGIC (LiveKit) ===
# =================================================================

async def main():
    """Main entry point for the robot app."""
    init_arduino()

    # Start sensor reader
    asyncio.create_task(sensor_reader_task())

    # Get LiveKit token
    resp = requests.get(TOKEN_URL)
    data = resp.json()
    token = data["token"]

    room = rtc.Room()

    room.on("connected", lambda: print("✅ Connected to LiveKit"))
    room.on("disconnected", lambda: print("❌ Disconnected from LiveKit"))

    # Data channel commands → Arduino motor/servo
    @room.on("data_received")
    def on_data_received(packet):
        try:
            msg = packet.data.decode("utf-8")
            payload = json.loads(msg)
            cmd = payload.get("cmd")

            if cmd == "set_direction":
                # LiveKit joystick: x (rudder), y (throttle)
                y_throttle = float(payload.get("y", 0.0))  # throttle
                x_rudder   = float(payload.get("x", 0.0))  # rudder
                serial_msg = f"DIR {y_throttle:.3f} {x_rudder:.3f}"
                send_cmd(serial_msg)
                return

            if cmd == "set_speed":
                speed = int(payload.get("value", 50))
                serial_msg = f"SPEED {speed}"
                send_cmd(serial_msg)
                return

            # Fallback simple commands
            if cmd == "forward":
                send_cmd("DIR 1.000 0.000")
            elif cmd == "back":
                send_cmd("DIR -1.000 0.000")
            elif cmd == "left":
                send_cmd("DIR 0.000 1.000")
            elif cmd == "right":
                send_cmd("DIR 0.000 -1.000")
            elif cmd == "stop":
                send_cmd("DIR 0 0")
            else:
                print("⚠️ Unknown command:", cmd)

        except Exception as e:
            print("❌ Error decoding LiveKit command:", e)

    await room.connect(ROOM_URL, token)

    # Camera
    camera = CameraStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    await room.local_participant.publish_track(track)

    print("📷 Video stream started")

    await camera.run()


if __name__ == "__main__":
    asyncio.run(main())
