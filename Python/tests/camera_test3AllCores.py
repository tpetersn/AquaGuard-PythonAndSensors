import torch
import cv2
from ultralytics import YOLO
from picamera2 import Picamera2, Preview
import time

# Use all CPU cores
torch.set_num_threads(4)

# Initialize Picamera2
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 480)}, display=None)
picam2.configure(config)
picam2.start()

# Get frame size for VideoWriter
w, h = 640, 480
fps = 30  # Picamera2 default FPS
video_writer = cv2.VideoWriter("instance-segmentation.avi",
                               cv2.VideoWriter_fourcc(*"mp4v"),
                               fps, (w, h))

# Load YOLO model
input_model = YOLO('yolo11n.pt')

print("Starting video capture... Press 'q' to quit.")
try:
    while True:
        frame = picam2.capture_array()  # returns XBGR8888 (4-channel)
        # Convert to 3-channel BGR
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        # Run YOLO
        results = input_model(frame, conf=0.5, device='cpu', imgsz=320)[0]
        annotated = results.plot()

        video_writer.write(annotated)
        cv2.imshow("YOLO", annotated)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    picam2.stop()
    video_writer.release()
    cv2.destroyAllWindows()
    print("Video capture stopped.")
