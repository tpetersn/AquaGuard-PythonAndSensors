import asyncio
import cv2
import json
from livekit import rtc
import requests

ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"


def gstreamer_pipeline(width=640, height=480, fps=30):
    return (
        f"libcamerasrc ! "
        f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
        f"videoconvert ! "
        f"video/x-raw,format=BGR ! "
        f"appsink"
    )


class CameraStream(rtc.VideoSource):
    def __init__(self, width=640, height=480, fps=30):
        super().__init__(width, height)
        self.width = width
        self.height = height
        self.fps = fps

        # --- Use CSI camera (libcamera + GStreamer) ---
        pipeline = gstreamer_pipeline(width, height, fps)
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        if not self.cap.isOpened():
            raise RuntimeError("❌ Failed to open CSI camera via GStreamer")

    async def run(self):
        frame_delay = 1.0 / self.fps

        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("⚠️ Failed to read from CSI camera")
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
            await asyncio.sleep(frame_delay)


# Movement handlers (unchanged)
def move_forward(): print("⬆️ Moving forward")
def move_back(): print("⬇️ Moving backward")
def turn_left(): print("⬅️ Turning left")
def turn_right(): print("➡️ Turning right")
def stop_motors(): print("⏹️ Stopping motors")


async def main():
    resp = requests.get(TOKEN_URL)
    TOKEN = resp.json()["token"]
    print("Got token:", TOKEN[:40], "...")

    room = rtc.Room()
    room.on("connected", lambda: print("✅ Connected to LiveKit"))

    @room.on("data_received")
    def on_data_received(packet):
        try:
            msg = packet.data.decode("utf-8")
            print("📩 Command:", msg)
            payload = json.loads(msg)
            cmd = payload.get("cmd")

            match cmd:
                case "forward": move_forward()
                case "back": move_back()
                case "left": turn_left()
                case "right": turn_right()
                case "stop": stop_motors()
                case _: print("⚠ Unknown cmd:", cmd)
        except Exception as e:
            print("❌ Decode error:", e)

    await room.connect(ROOM_URL, TOKEN)

    camera = CameraStream(640, 480, fps=30)
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)
    pub = await room.local_participant.publish_track(track)
    print("📡 Published Track:", pub.sid)

    await camera.run()


if __name__ == "__main__":
    asyncio.run(main())
