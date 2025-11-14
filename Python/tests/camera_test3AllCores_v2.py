import torch
import cv2
from ultralytics import YOLO
from picamera2 import Picamera2, Preview
import time
from ultralytics import solutions


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
visioneye = solutions.VisionEye(
    show=True,  # display the output
    model="yolo11n.pt",  # use any model that Ultralytics support, i.e, YOLOv10
    classes=[0, 2],  # generate visioneye view for specific classes
    vision_point=(320, 320),  # the point, where vision will view objects and draw tracks
    conf =0.5,
)

print("Starting video capture... Press 'q' to quit.")
try:
    while True:
        frame = picam2.capture_array()  # returns XBGR8888 (4-channel)
        # Convert to 3-channel BGR
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        # Run YOLO
        results = visioneye(frame)
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
