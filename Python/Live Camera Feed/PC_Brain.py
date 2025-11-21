import asyncio
import cv2
import imagezmq
import numpy as np
import requests
from livekit import rtc
from ultralytics import YOLO

# --- CONFIGURATION ---
# 1. LIVEKIT SETTINGS (Masquerading as the Raspberry Pi)
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
# We use 'identity=raspberry' so the dashboard thinks this IS the robot
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

# 2. CONTROL SETTINGS
model = YOLO("yolo11n.pt")
TARGET_CLASS_ID = 0       # Person
STOP_DISTANCE = 0.6       
FORWARD_SPEED = 0.4       
STEERING_SENSITIVITY = 0.7

# --- VIDEO PUBLISHER CLASS ---
class ProcessedVideoSource(rtc.VideoSource):
    def __init__(self):
        super().__init__(640, 480)

    def publish_frame(self, cv2_frame):
        # Resize to standard resolution
        frame = cv2.resize(cv2_frame, (640, 480))
        # Convert BGR (OpenCV) -> YUV (LiveKit)
        frame_yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
        
        video_frame = rtc.VideoFrame(
            width=640,
            height=480,
            data=frame_yuv.tobytes(),
            type=rtc.VideoBufferType.I420,
        )
        self.capture_frame(video_frame)

async def main():
    # --- SETUP ZMQ (Listen for Pi) ---
    image_hub = imagezmq.ImageHub()
    print("🧠 Laptop Brain Listening for Pi on Port 5555...")

    # --- SETUP LIVEKIT (Connect to Dashboard) ---
    print("☁️ Connecting to LiveKit as 'raspberry'...")
    try:
        resp = requests.get(TOKEN_URL)
        token = resp.json()["token"]
        room = rtc.Room()
        await room.connect(ROOM_URL, token)
        
        # Publish the video track
        video_source = ProcessedVideoSource()
        track = rtc.LocalVideoTrack.create_video_track("camera", video_source)
        await room.local_participant.publish_track(track)
        print("✅ Dashboard Stream Active! (Website will show YOLO view)")
    except Exception as e:
        print(f"⚠️ LiveKit Error (Continuing offline): {e}")

    # --- MAIN LOOP ---
    try:
        while True:
            # A. Receive Frame from Pi (via WiFi)
            # We use asyncio.to_thread to avoid blocking the LiveKit connection
            rpi_name, jpg_buffer = await asyncio.to_thread(image_hub.recv_jpg)
            frame = cv2.imdecode(np.frombuffer(jpg_buffer, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            height, width, _ = frame.shape
            center_x, center_y = width // 2, height // 2

            # B. YOLO Inference
            throttle_val = 0.0
            turn_val = 0.0
            command_text = "SEARCHING"
            color = (0, 0, 255) # Red

            results = model.track(frame, persist=True, verbose=False)
            
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                class_ids = results[0].boxes.cls.int().cpu().numpy()
                
                for box, cls in zip(boxes, class_ids):
                    if int(cls) != TARGET_CLASS_ID: continue

                    x1, y1, x2, y2 = box
                    obj_center_x = int((x1 + x2) / 2)
                    obj_center_y = int((y1 + y2) / 2)
                    obj_height = y2 - y1
                    
                    # Logic: Distance & Steering
                    pixel_coverage = obj_height / height
                    raw_error = (obj_center_x - center_x) / (width / 2)
                    turn_val = max(-1.0, min(1.0, raw_error * STEERING_SENSITIVITY))

                    if pixel_coverage > STOP_DISTANCE:
                        command_text = "STOP (Arrived)"
                        color = (0, 0, 255)
                    else:
                        throttle_val = FORWARD_SPEED
                        command_text = "TRACKING"
                        color = (0, 255, 0)

                    # Draw Visuals (These will appear on Dashboard)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 4)
                    cv2.line(frame, (center_x, center_y), (obj_center_x, obj_center_y), color, 2)
                    cv2.putText(frame, f"{command_text} T:{turn_val:.2f}", (int(x1), int(y1)-10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    break

            # C. Send Command Back to Pi
            final_cmd = f"DIR {throttle_val:.3f} {turn_val:.3f}"
            image_hub.send_reply(final_cmd.encode("utf-8"))
            print(f"cmd: {final_cmd}")

            # D. Stream to Dashboard
            video_source.publish_frame(frame)

            # E. Show Locally
            cv2.imshow("Laptop Brain", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
            await asyncio.sleep(0)

    finally:
        await room.disconnect()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    asyncio.run(main())