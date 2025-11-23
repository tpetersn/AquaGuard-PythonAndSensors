import asyncio
import cv2
import json
import re
import requests
import serial
import time
from livekit import rtc
# NOTE: Ensure SendReadings.py is available and contains the post_reading function
from SendReadings import post_reading 

# =================================================================
# === CONFIGURATION CONSTANTS ===
# =================================================================

# --- LiveKit Config ---
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

# --- Arduino Serial Config ---
# Ensure this port matches your connected Arduino/Nano
ARDUINO_PORT = "/dev/ttyUSB0"  # Linux/Raspberry Pi (Default from sensor script)
# ARDUINO_PORT = "COM3"           # Windows (Default from LiveKit script)
BAUD = 9600                     # Must match Arduino's Serial.begin(9600)

# --- External Service Config ---
DEVICE_ID = "68cc90c7ef0763dddf1a5e9d"  # Your actual device ID

# Arbitrary values for fields not measured by Arduino (Chlorine, Battery)
CHLORINE = 1.1
BATTERY_VOLTAGE = 3.7
BATTERY_PERCENTAGE = 85

# Regex to capture all structured data fields from the Arduino output
# Format: DATA:T1=25.50,T2=22.30,TDS=350,pH=7.21,AccelZ=-9.81,Orient=Upright
DATA_PATTERN = re.compile(
    r"DATA:T1=([\d.-]+|ERR),T2=([\d.-]+|ERR),TDS=(\d+),pH=([\d.]+),AccelZ=([\d.-]+),Orient=([a-zA-Z\s]+)"
)

# =================================================================
# === GLOBAL STATE & UTILITIES ===
# =================================================================

arduino = None

def init_arduino():
    """Initializes the global serial connection."""
    global arduino
    try:
        # Use a non-blocking timeout of 0 to poll the serial port quickly
        arduino = serial.Serial(ARDUINO_PORT, BAUD, timeout=0)
        time.sleep(2)  # Wait for Arduino auto-reset
        print(f"🔌 Arduino connected on {ARDUINO_PORT} at {BAUD} baud!")
        arduino.reset_input_buffer()
    except Exception as e:
        print("❌ Could not connect to Arduino:", e)

def send_cmd(cmd: str):
    """Send simple text command to Arduino."""
    if arduino and arduino.is_open:
        arduino.write((cmd + "\n").encode("utf-8"))
        print("➡️ Sent to Arduino:", cmd)
    else:
        print("⚠️ Arduino not connected! Command failed:", cmd)


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
        """Continuously captures video frames and publishes them."""
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
            await asyncio.sleep(0.03) # ~33 FPS


# =================================================================
# === SENSOR READER TASK (runs concurrently) ===
# =================================================================

# =================================================================
# === SENSOR READER TASK (runs concurrently) ===
# =================================================================

async def sensor_reader_task():
    """
    Reads sensor data from the Arduino serial port, parses it, and posts it.
    This runs in a dedicated thread to avoid blocking the main asyncio loop 
    with pyserial's blocking calls.
    """
    if not arduino:
        print("Sensor reader stopped: Arduino not initialized.")
        return

    print("📡 Sensor reader task started. Awaiting data...")

    # Blocking function that will be run in a separate thread
    def read_and_process():
        if arduino.in_waiting > 0:
            try:
                line = arduino.readline().decode("utf-8", errors="ignore").strip()
            except Exception as e:
                print(f"❌ Error reading from Arduino: {e}")
                return

            if not line:
                return

            # Debug: show the raw line exactly as received
            print("🔎 Raw line from Arduino:", repr(line))

            # Only parse lines that start with "DATA:"
            if line.startswith("DATA:"):
                try:
                    # Remove the "DATA:" prefix
                    payload = line.split("DATA:", 1)[1]

                    # Example payload:
                    # "T1=25.50,T2=22.30,TDS=350,pH=7.21,AccelZ=-9.81,Orient=Upright"
                    parts = payload.split(",")

                    data = {}
                    for part in parts:
                        if "=" in part:
                            key, val = part.split("=", 1)
                            data[key.strip()] = val.strip()

                    # Extract values with sane defaults
                    t1_str = data.get("T1", "ERR")
                    tds_str = data.get("TDS", "0")
                    ph_str  = data.get("pH", "7.0")
                    orientation = data.get("Orient", "Unknown")
                    pitch_str = data.get("Pitch")
                    roll_str = data.get("Roll")
                    

                    temperature = float(t1_str) if t1_str != "ERR" else None
                    tds = float(tds_str)
                    ph = float(ph_str)

                    pitch = float(pitch_str) if pitch_str not in (None, "ERR", "") else None
                    roll  = float(roll_str)  if roll_str  not in (None, "ERR", "") else None

                    print("-" * 25)
                    print(f"🌡️ T1={temperature}°C | pH={ph} | TDS={tds}")
                    print(f"📐 Orientation: {orientation} | Pitch={pitch}° | Roll={roll}°")

                    # Post the reading
                    response = post_reading(
                        DEVICE_ID,
                        temperature=temperature,
                        ph=ph,
                        chlorine=CHLORINE,
                        tds=tds,
                        battery_voltage=BATTERY_VOLTAGE,
                        battery_percentage=BATTERY_PERCENTAGE,
                        pitch=pitch,
                        roll=roll
                    )

                    print(
                        "✅ Reading sent successfully:",
                        getattr(response, "status_code", "OK")
                    )
                    print("-" * 25)

                except Exception as e:
                    print(f"❌ Error processing DATA line '{line}': {e}")

            else:
                # Any other message from Arduino (debug, motor feedback, etc.)
                print(f"💬 Arduino Message: {line}")

    # Main async loop: call blocking reader in a thread repeatedly
    while True:
        await asyncio.to_thread(read_and_process)
        await asyncio.sleep(0.1)  # Check serial input frequently



# =================================================================
# === MAIN ASYNC LOGIC (LiveKit connection) ===
# =================================================================

async def main():
    """Main entry point for the LiveKit robot application."""
    init_arduino()

    # Start the concurrent sensor reading task
    asyncio.create_task(sensor_reader_task())
    print("🚀 Sensor reading task scheduled.")

    # Get token from backend
    resp = requests.get(TOKEN_URL)
    data = resp.json()
    TOKEN = data["token"]
    print("Got token:", TOKEN[:40], "...")

    room = rtc.Room()

    room.on("connected", lambda: print("✅ Connected to LiveKit"))
    room.on("disconnected", lambda: print("❌ Disconnected from LiveKit"))

    # Listen for commands from LiveKit data channel
    @room.on("data_received")
    def on_data_received(packet):
        try:
            msg = packet.data.decode("utf-8")
            payload = json.loads(msg)
            cmd = payload.get("cmd")

            # --- Joystick analog direction ---
            if cmd == "set_direction":
                # Note: LiveKit payload uses (x, y) for joystick, we need to map to (throttle, rudder)
                # Assuming x (payload) is rudder and y (payload) is throttle
                y_throttle = float(payload.get("y", 0)) # Mapped to X in Arduino (throttle)
                x_rudder = float(payload.get("x", 0))   # Mapped to Y in Arduino (rudder)
                
                # Arduino expects "DIR {x: throttle} {y: rudder}"
                serial_msg = f"DIR {y_throttle:.3f} {x_rudder:.3f}" 
                send_cmd(serial_msg)
                return

            # --- Speed control ---
            if cmd == "set_speed":
                speed = int(payload.get("value", 50))
                serial_msg = f"SPEED {speed}"
                print("📩 Speed:", serial_msg)
                send_cmd(serial_msg)
                return

            # --- Simple fallback digital commands ---
            print("📩 Received:", cmd)
            if cmd == "forward":
                send_cmd("DIR 1.000 0.000")
            elif cmd == "back":
                send_cmd("DIR -1.000 0.000")
            elif cmd == "left":
                send_cmd("DIR 0.000 1.000") # Full rudder left (assuming negative X is left in original Arduino code)
            elif cmd == "right":
                send_cmd("DIR 0.000 -1.000") # Full rudder right
            elif cmd == "stop":
                send_cmd("DIR 0 0")
            else:
                print("⚠️ Unknown command:", cmd)

        except Exception as e:
            print("❌ Error decoding command:", e)


    await room.connect(ROOM_URL, TOKEN)

    # Setup camera stream
    camera = CameraStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    await room.local_participant.publish_track(track)

    print("📷 Video stream started")

    # The main task runs the camera stream indefinitely
    await camera.run()


if __name__ == "__main__":
    # Ensure correct mapping for control:
    # LiveKit Joystick Y -> Arduino X (Throttle)
    # LiveKit Joystick X -> Arduino Y (Rudder)
    asyncio.run(main())