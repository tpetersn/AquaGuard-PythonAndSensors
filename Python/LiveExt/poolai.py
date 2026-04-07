import os, cv2, numpy as np, asyncio, requests
from pathlib import Path
from dataclasses import dataclass
from ultralytics import YOLO
from livekit import rtc
from PostAlertToDb import send_alert
import time

# ================= CONFIG =================
BEST_SEG = "best.pt"
OUT_ROOT = "annotations"
os.makedirs(OUT_ROOT, exist_ok=True)

seg_model  = YOLO(BEST_SEG)
det_model  = YOLO("yolov8n.pt")  # Person detection

@dataclass
class CFG:
    seg_conf: float = 0.05
    imgsz: int = 960
    min_blob_area: int = 1500
    fps_fallback: float = 30.0

C = CFG()

ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=garage&roomName=pool"

DEVICE_ID = "68cc90c7ef0763dddf1a5e9d"

# ================= SELECT SOURCE =================
def download_youtube(url):
    import yt_dlp
    ydl_opts = {
        "format": "mp4",
        "outtmpl": "temp_video.%(ext)s",
        "quiet": False,
        "js_runtime": "node",  # <-- tell yt_dlp to use Node.js
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

choice = input("Use camera or video? (cam/vid): ").strip().lower()
if choice == "cam":
    SOURCE = 0
else:
    url_or_path = input("Enter video path or YouTube URL: ").strip()
    if url_or_path.startswith("http"):
        SOURCE = download_youtube(url_or_path)
        print("✅ Video downloaded:", SOURCE)
    else:
        SOURCE = url_or_path

# ================= HELPERS =================
def seg_water_mask(img_bgr):
    H, W = img_bgr.shape[:2]
    r = seg_model.predict(img_bgr, conf=C.seg_conf, imgsz=C.imgsz, verbose=False)[0]

    mask = np.zeros((H, W), dtype=np.uint8)
    if r.masks is not None:
        for m in r.masks.data.cpu().numpy():
            m = (m * 255).astype(np.uint8)
            m = cv2.resize(m, (W, H))
            mask = np.maximum(mask, m)
    return (mask > 127).astype(np.uint8)

def detect_person(frame, water_mask):
    results = det_model.predict(frame, imgsz=C.imgsz, conf=0.3, verbose=False)[0]

    person_in_pool = False

    # 🔥 Safety check
    if water_mask is None:
        return frame, False

    h_mask, w_mask = water_mask.shape[:2]

    for box, cls in zip(results.boxes.xyxy.cpu().numpy(),
                        results.boxes.cls.cpu().numpy()):

        cls = int(cls)
        if det_model.names[cls] != "person":
            continue

        x1, y1, x2, y2 = box.astype(int)

        # ✅ Clamp to BOTH frame AND mask
        x1 = max(0, min(x1, w_mask))
        y1 = max(0, min(y1, h_mask))
        x2 = max(0, min(x2, w_mask))
        y2 = max(0, min(y2, h_mask))

        # 🔥 Prevent invalid slices
        if x2 <= x1 or y2 <= y1:
            continue

        person_roi = water_mask[y1:y2, x1:x2]

        # 🔥 Extra safety
        if person_roi.size == 0:
            continue

        # % of water inside the person box
        water_ratio = np.sum(person_roi) / (person_roi.size + 1e-6)

        if water_ratio > 0.35:
            color = (0, 0, 255)
            person_in_pool = True
        else:
            color = (0, 255, 0)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    return frame, person_in_pool

# ================= CAMERA / VIDEO STREAM =================
class PoolStream(rtc.VideoSource):
    def __init__(self, width=640, height=480):
        super().__init__(width, height)
        self.cap = cv2.VideoCapture(SOURCE)
        self.width = width
        self.height = height
        self.alert_sent = False
        self.frame_count = 0
        self.process_every = 20   # 🔥 adjust this for speed vs accuracy
        self.last_mask = None
        self.last_person = False
        self.last_alert_time = 0
        self.alert_cooldown = 15  

    async def run(self):
        while True:
            
            ret, frame = self.cap.read()
            if not ret:
                await asyncio.sleep(0.05)
                continue
            
            frame = cv2.resize(frame, (self.width, self.height))
            self.frame_count += 1
            run_ai = (self.frame_count % self.process_every == 0)

            # Fix green screen for videos
            if len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif len(frame.shape) == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            # Water segmentation
            if run_ai:
                mask = seg_water_mask(frame)
                self.last_mask = mask

                frame, person_detected = detect_person(frame, mask)
                self.last_person = person_detected
            else:
                mask = self.last_mask
                person_detected = self.last_person
            if mask is not None:
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(frame, contours, -1, (0,255,255), 2)           # ===== Person detection =====
            frame, person_detected = detect_person(frame, mask)

            # ===== Alert if person in water =====
            now = time.time()

            if person_detected:
                if now - self.last_alert_time > self.alert_cooldown:
                    try:
                        print("🚨 ALERT SENT")

                        send_alert(
                            DEVICE_ID,
                            alert_type="pool_intrusion",
                            message="Person detected inside pool",
                            severity="critical"
                        )

                        self.last_alert_time = now

                    except Exception as e:
                        print("Alert error:", e)
            elif not person_detected:
                self.alert_sent = False
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif frame.shape[2] == 1:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            # ===== Convert to YUV and send to LiveKit =====
            # Convert to YUV and publish to LiveKit
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            video_frame = rtc.VideoFrame(
                width=self.width,
                height=self.height,
                data=yuv.tobytes(),
                type=rtc.VideoBufferType.I420
            )
            self.capture_frame(video_frame)

            cv2.imshow("Preview", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            await asyncio.sleep(0.03)

        self.cap.release()
        cv2.destroyAllWindows()

# ================= MAIN =================
async def main():
    token = requests.get(TOKEN_URL).json()["token"]
    room = rtc.Room()
    await room.connect(ROOM_URL, token)
    print("✅ Connected to LiveKit")

    stream = PoolStream(640, 480)
    track = rtc.LocalVideoTrack.create_video_track("pool-camera-2", stream)
    await room.local_participant.publish_track(track)
    print("📡 Streaming started")

    await stream.run()

if __name__ == "__main__":
    asyncio.run(main())
