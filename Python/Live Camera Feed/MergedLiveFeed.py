import asyncio
import cv2
import json
import time
import socket
import serial
import imagezmq
import requests
from livekit import rtc

# ======================================================
# CONFIGURATION
# ======================================================
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"
SETTINGS_URL = "https://pbrobot.onrender.com/api/settings"

# Laptop Brain for AUTO mode
LAPTOP_IP = "192.168.1.XXX"

# Arduino serial port
ARDUINO_PORT = "/dev/ttyACM0"   # Pi
BAUD = 9600

# ======================================================
# ARDUINO SETUP
# ======================================================
arduino = None


def init_arduino():
    global arduino
    try:
        arduino = serial.Serial(ARDUINO_PORT, BAUD, timeout=1)
        time.sleep(2)
        print("🔌 Arduino connected!")
    except Exception as e:
        print("❌ Arduino error:", e)
        arduino = None


def send_cmd(cmd: str):
    if arduino and arduino.is_open:
        arduino.write((cmd + "\n").encode("utf-8"))
        print("➡️ Arduino:", cmd)
    else:
        print(f"⚠️ Arduino disconnected | {cmd}")


# ======================================================
# AUTH0 TOKEN FOR SETTINGS
# ======================================================
AUTH0_URL = "https://dev-1uv6k6fg33hn7eoe.us.auth0.com/oauth/token"
CLIENT_ID = "FJnwHhH8HBqL2nu8rHoyPwtVVRwApRJ5"
CLIENT_SECRET = "bS9JqG-EsdfuU4dVa662CVdXzHjg8NW0sVwMylHKE16TxgJwAO20evCqxaxyXF89"
AUDIENCE = "https://pbrobot.onrender.com/"

_token = None
_token_expiry = 0


def _get_token():
    global _token, _token_expiry
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "audience": AUDIENCE,
        "grant_type": "client_credentials",
    }
    r = requests.post(AUTH0_URL, json=payload)
    r.raise_for_status()
    data = r.json()
    _token = data["access_token"]
    _token_expiry = time.time() + data["expires_in"] - 60


def get_token():
    global _token
    if _token is None or time.time() >= _token_expiry:
        _get_token()
    return _token


def fetch_auto_mode():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(SETTINGS_URL, headers=headers)
    r.raise_for_status()
    return r.json().get("autoRoamOn", False)


# ======================================================
# AUTO MODE CONTROLLER
# ======================================================
def run_auto_mode():
    print("🤖 AUTO MODE ENABLED")
    sender = imagezmq.ImageSender(connect_to=f"tcp://{LAPTOP_IP}:5555")

    cap = cv2.VideoCapture(0)
    cap.set(3, 640)
    cap.set(4, 480)
    time.sleep(1)

    name = socket.gethostname()

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        ret_code, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        reply = sender.send_jpg(name, jpg)
        cmd = reply.decode()

        send_cmd(cmd)

        # If switched to manual mode, exit
        if not fetch_auto_mode():
            print("🔄 Switching to MANUAL mode…")
            cap.release()
            return


# ======================================================
# MANUAL MODE VIA LIVEKIT
# ======================================================
class CameraStream(rtc.VideoSource):
    def __init__(self):
        super().__init__(640, 480)
        self.cap = cv2.VideoCapture(0)

    async def run(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame = cv2.resize(frame, (640, 480))
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)

            video_frame = rtc.VideoFrame(
                width=640,
                height=480,
                data=yuv.tobytes(),
                type=rtc.VideoBufferType.I420,
            )
            self.capture_frame(video_frame)
            await asyncio.sleep(0.03)


async def run_manual_mode():
    print("🎮 MANUAL MODE ENABLED")
    init_arduino()

    # fetch token
    r = requests.get(TOKEN_URL)
    TOKEN = r.json()["token"]

    room = rtc.Room()

    @room.on("data_received")
    def on_data_received(packet):
        try:
            msg = json.loads(packet.data.decode())
            cmd = msg.get("cmd")

            if cmd == "set_direction":
                x = float(msg.get("x", 0))
                y = float(msg.get("y", 0))
                send_cmd(f"DIR {x:.3f} {y:.3f}")
                return

            if cmd == "stop":
                send_cmd("DIR 0 0")
                return

        except Exception as e:
            print("⚠️ Error:", e)

    await room.connect(ROOM_URL, TOKEN)

    cam = CameraStream()
    track = rtc.LocalVideoTrack.create_video_track("pi", cam)
    await room.local_participant.publish_track(track)

    print("📷 camera streaming...")

    # Loop manual mode until mode changes
    while fetch_auto_mode() is False:
        await cam.run()

    print("🔄 Switching to AUTO…")
    await room.disconnect()


# ======================================================
# MODE SWITCHER
# ======================================================
async def mode_loop():
    print("🚀 Robot controller started!")
    init_arduino()

    while True:
        auto = fetch_auto_mode()

        if auto:
            run_auto_mode()
        else:
            await run_manual_mode()

        await asyncio.sleep(1)


# ======================================================
# MAIN
# ======================================================
if __name__ == "__main__":
    asyncio.run(mode_loop())
