
import asyncio
import cv2
from livekit import rtc
import requests
from ultralytics import solutions, YOLO

# Get token from your API
ROOM_URL = "wss://your-project.livekit.cloud"

# ?? Replace with your deployed API endpoint on Render (or local for testing)
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

input_model = YOLO ('yolo11n.pt')  # load a pretrained YOLOv11 nano model)



ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"  # from LiveKit Cloud

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

            results = input_model(frame, conf=0.5, device='cpu', imgsz=640)[0] # predict on the frame on model
            annotated = results.plot()  #annotate the frame

            frame = cv2.resize(annotated, (self.width, self.height))

            # Convert from BGR ? I420 (YUV420p)
            frame_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)

            # ? Build VideoFrame with type
            video_frame = rtc.VideoFrame(
                width=self.width,
                height=self.height,
                data=frame_yuv.tobytes(),
                type=rtc.VideoBufferType.I420
            )

            self.capture_frame(video_frame)
            await asyncio.sleep(0.03)


# --- Main Logic ---
async def main():
    # Get token from backend
    resp = requests.get(TOKEN_URL)
    data = resp.json()
    TOKEN = data["token"]
    print("Got token:", TOKEN[:40], "...")  # just preview

    # Connect to LiveKit room
    room = rtc.Room()

    # Debug event listeners
    room.on("connected", lambda: print("? Connected to LiveKit"))
    room.on("disconnected", lambda: print("? Disconnected from LiveKit"))
    room.on("participant_connected", lambda p: print(f"?? Participant joined: {p.identity}"))
    room.on("participant_disconnected", lambda p: print(f"?? Participant left: {p.identity}"))

    await room.connect(ROOM_URL, TOKEN)

    # Setup camera stream
    camera = CameraStream(640, 480)

    # Wrap source into a LocalVideoTrack
    track = rtc.LocalVideoTrack.create_video_track("pi-camera", camera)

    # Publish track to the room
    pub = await room.local_participant.publish_track(track)
    print("? Track publish request done:", pub.sid)

    # Start camera capture loop
    await camera.run()


if __name__ == "__main__":
    asyncio.run(main())
