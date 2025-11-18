import asyncio
import cv2
import json
from livekit import rtc
import requests
import serial
import time

# LiveKit config
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

# --- Arduino Serial Setup ---
# Change COM port if needed:
# ARDUINO_PORT = "/dev/ttyACM0"   # Linux/Raspberry Pi
ARDUINO_PORT = "COM3"         # Windows
BAUD = 9600

arduino = None

def init_arduino():
    global arduino
    try:
        arduino = serial.Serial(ARDUINO_PORT, BAUD, timeout=1)
        time.sleep(2)  # Arduino auto-resets on connection
        print("🔌 Arduino connected!")
    except Exception as e:
        print("❌ Could not connect to Arduino:", e)

def send_cmd(cmd: str):
    """Send simple text command to Arduino."""
    if arduino and arduino.is_open:
        arduino.write((cmd + "\n").encode("utf-8"))
        print("➡️ Sent to Arduino:", cmd)
    else:
        print("⚠️ Arduino not connected!")

# --- Camera Publisher ---
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
            await asyncio.sleep(0.03)


# --- Robot Control Handlers ---
def move_forward():
    print("⬆️ Moving forward")
    send_cmd("forward")

def move_back():
    print("⬇️ Moving backward")
    send_cmd("back")

def turn_left():
    print("⬅️ Turning left")
    send_cmd("left")

def turn_right():
    print("➡️ Turning right")
    send_cmd("right")

def stop_motors():
    print("⏹️ Stopping motors")
    send_cmd("stop")


# --- Main Logic ---
async def main():
    init_arduino()

    # Get token from backend
    resp = requests.get(TOKEN_URL)
    data = resp.json()
    TOKEN = data["token"]
    print("Got token:", TOKEN[:40], "...")

    room = rtc.Room()

    room.on("connected", lambda: print("✅ Connected to LiveKit"))
    room.on("disconnected", lambda: print("❌ Disconnected from LiveKit"))

    # Listen for commands
    @room.on("data_received")
    def on_data_received(packet):
        try:
            msg = packet.data.decode("utf-8")
            payload = json.loads(msg)
            cmd = payload.get("cmd")

            # --- Joystick analog direction ---
            if cmd == "set_direction":
                y = float(payload.get("x", 0))
                x = float(payload.get("y", 0))
                serial_msg = f"DIR {x:.3f} {y:.3f}"
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
                send_cmd("DIR 0 -1")
            elif cmd == "back":
                send_cmd("DIR 0 1")
            elif cmd == "left":
                send_cmd("DIR -1 0")
            elif cmd == "right":
                send_cmd("DIR 1 0")
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

    await camera.run()


if __name__ == "__main__":
    asyncio.run(main())
