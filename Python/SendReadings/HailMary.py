import asyncio
import cv2
import json
import re
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

# Update this to your actual serial port. On Windows "COM3", on Raspberry Pi "/dev/ttyACM0" or "/dev/ttyUSB0".
ARDUINO_PORT = "/dev/ttyUSB0"
BAUD = 9600

DEVICE_ID = "68cc90c7ef0763dddf1a5e9d"

CHLORINE = 1.1
BATTERY_VOLTAGE = 3.7
BATTERY_PERCENTAGE = 85

# Regex to match exact Arduino DATA line:
DATA_PATTERN = re.compile(
    r"DATA:T1=([\d.-]+|ERR),T2=([\d.-]+|ERR),TDS=(\d+),pH=([\d.]+),AccelZ=([\d.-]+),Orient=([a-zA-Z\s]+)"
)

# =================================================================
# === GLOBAL STATE ===
# =================================================================
arduino = None

def init_arduino():
    """Initializes the global serial connection with a small blocking timeout for reliable readline()."""
    global arduino
    try:
        # Use timeout=1 (1 second) so readline() will wait briefly for a full line ending with '\n'.
        arduino = serial.Serial(ARDUINO_PORT, BAUD, timeout=1)
        time.sleep(2)  # Give Arduino time to reset if it auto-resets on serial open
        arduino.reset_input_buffer()
        print(f"🔌 Arduino connected on {ARDUINO_PORT} at {BAUD} baud!")
    except Exception as e:
        arduino = None
        print("❌ Could not connect to Arduino:", e)

def send_cmd(cmd: str):
    """Send simple text command to Arduino (with newline)."""
    if arduino and arduino.is_open:
        try:
            arduino.write((cmd + "\n").encode("utf-8"))
            print("➡️ Sent to Arduino:", cmd)
        except Exception as e:
            print("❌ Failed to send command to Arduino:", e)
    else:
        print("⚠️ Arduino not connected! Command failed:", cmd)

# =================================================================
# === CAMERA STREAMER (unchanged) ===
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
# === SENSOR READER TASK (robust) ===
# =================================================================
async def sensor_reader_task():
    """
    Runs a blocking serial read loop inside a thread, decodes full lines,
    parses structured DATA: lines and calls post_reading().
    """

    if not arduino:
        print("Sensor reader stopped: Arduino not initialized.")
        return

    print("📡 Sensor reader task started. Awaiting data...")

    def blocking_serial_loop():
        """This runs in a background thread — do blocking readline() here."""
        while True:
            try:
                # Blocking call with timeout (set in init_arduino). Returns a bytes object (may be b'' on timeout).
                raw = arduino.readline()
            except Exception as e:
                print("❌ Serial read error:", e)
                # Sleep briefly before retrying to avoid busy-loop on fatal errors
                time.sleep(1)
                continue

            if not raw:
                # Timeout without data: simply continue
                continue

            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception as e:
                print("❌ Decode error for raw serial data:", e)
                continue

            # DEBUG: Always print raw line so we can see what arrives
            print(f"🔷 RAW LINE: {line}")

            # Attempt to parse the structured DATA line
            match = DATA_PATTERN.search(line)
            print(match)
            if match:
                try:
                    tempC1_str, tempC2_str, tds_str, ph_str, accelZ_str, orientation = match.groups()
                    temperature = float(tempC1_str) if tempC1_str != "ERR" else None
                    tds = int(tds_str)
                    ph = float(ph_str)

                    print("-" * 40)
                    print(f"Parsed -> T1={temperature}, pH={ph}, TDS={tds}, Orient={orientation}")
                    print("Posting to API...")

                    try:
                        response = post_reading(
                            DEVICE_ID,
                            temperature=temperature,
                            ph=ph,
                            chlorine=CHLORINE,
                            tds=tds,
                            battery_voltage=BATTERY_VOLTAGE,
                            battery_percentage=BATTERY_PERCENTAGE
                        )
                        # If post_reading returns a requests.Response or similar, show status_code; otherwise just show repr
                        status = getattr(response, "status_code", None)
                        if status is not None:
                            print(f"✅ Reading posted, status_code={status}")
                        else:
                            print("✅ Reading posted, response:", response)
                    except Exception as e:
                        print("❌ post_reading raised an exception:", e)

                    print("-" * 40)

                except Exception as e:
                    print(f"❌ Error parsing DATA line '{line}': {e}")

            else:
                # Non-DATA lines: print for debug (motor logs, test messages, etc.)
                print("💬 Arduino message (non-DATA):", line)

            # small sleep is not necessary because readline blocks, but keep tiny pause for thread scheduling
            time.sleep(0.001)

    # Run the blocking serial loop in a thread so it doesn't block the main asyncio loop.
    await asyncio.to_thread(blocking_serial_loop)

# =================================================================
# === MAIN ASYNC LOGIC (LiveKit connection) ===
# =================================================================
async def main():
    init_arduino()

    # schedule serial reader
    asyncio.create_task(sensor_reader_task())
    print("🚀 Sensor reading task scheduled.")

    # fetch token
    try:
        resp = requests.get(TOKEN_URL, timeout=5)
        data = resp.json()
        TOKEN = data["token"]
        print("Got token:", TOKEN[:40], "...")
    except Exception as e:
        print("❌ Failed to obtain token:", e)
        TOKEN = None

    if TOKEN is None:
        print("⚠️ No token available — skipping LiveKit connection.")
        # Wait forever or exit — choose to exit here
        return

    room = rtc.Room()
    room.on("connected", lambda: print("✅ Connected to LiveKit"))
    room.on("disconnected", lambda: print("❌ Disconnected from LiveKit"))

    @room.on("data_received")
    def on_data_received(packet):
        try:
            msg = packet.data.decode("utf-8")
            payload = json.loads(msg)
            cmd = payload.get("cmd")

            if cmd == "set_direction":
                y_throttle = float(payload.get("y", 0))
                x_rudder = float(payload.get("x", 0))
                serial_msg = f"DIR {y_throttle:.3f} {x_rudder:.3f}"
                send_cmd(serial_msg)
                return

            if cmd == "set_speed":
                speed = int(payload.get("value", 50))
                send_cmd(f"SPEED {speed}")
                return

            print("📩 Received:", cmd)
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
            print("❌ Error decoding command:", e)

    await room.connect(ROOM_URL, TOKEN)

    camera = CameraStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    await room.local_participant.publish_track(track)

    print("📷 Video stream started")

    await camera.run()

if __name__ == "__main__":
    asyncio.run(main())
