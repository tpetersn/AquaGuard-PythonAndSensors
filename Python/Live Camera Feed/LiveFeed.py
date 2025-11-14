import asyncio
import cv2
import json
from livekit import rtc
import requests

# LiveKit config
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"


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
    # TODO: Replace with GPIO control

def move_back():
    print("⬇️ Moving backward")
    # TODO: Replace with GPIO control

def turn_left():
    print("⬅️ Turning left")
    # TODO: Replace with GPIO control

def turn_right():
    print("➡️ Turning right")
    # TODO: Replace with GPIO control

def stop_motors():
    print("⏹️ Stopping motors")
    # TODO: Replace with GPIO control


# --- Main Logic ---
async def main():
    # Get token from backend
    resp = requests.get(TOKEN_URL)
    data = resp.json()
    TOKEN = data["token"]
    print("Got token:", TOKEN[:40], "...")

    # Connect to LiveKit room
    room = rtc.Room()

    # Debug event listeners
    room.on("connected", lambda: print("✅ Connected to LiveKit"))
    room.on("disconnected", lambda: print("❌ Disconnected from LiveKit"))
    room.on("participant_connected", lambda p: print(f"👤 Participant joined: {p.identity}"))
    room.on("participant_disconnected", lambda p: print(f"👤 Participant left: {p.identity}"))

    # Listen for commands via DataChannel
    @room.on("data_received")
    def on_data_received(packet):
        try:
            # Extract raw bytes from DataPacket
            raw = packet.data
            msg = raw.decode("utf-8")

            print(f"📩 Command received: {msg}")

            import json
            payload = json.loads(msg)
            cmd = payload.get("cmd")

            if cmd == "forward":
                move_forward()
            elif cmd == "back":
                move_back()
            elif cmd == "left":
                turn_left()
            elif cmd == "right":
                turn_right()
            elif cmd == "stop":
                stop_motors()
            else:
                print("⚠️ Unknown command:", cmd)

        except Exception as e:
            print("❌ Error decoding command:", e)

    await room.connect(ROOM_URL, TOKEN)

    # Setup camera stream
    camera = CameraStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    pub = await room.local_participant.publish_track(track)
    print("✅ Track publish request done:", pub.sid)

    # Start camera capture loop
    await camera.run()


if __name__ == "__main__":
    asyncio.run(main())
