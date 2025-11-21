import cv2
from ultralytics import YOLO

model = YOLO("yolo11n.pt")
cap = cv2.VideoCapture(0)

# --- CONFIGURATION ---
TARGET_CLASS_ID = 0       # Person
STOP_DISTANCE = 0.99       # Stop when object is 99% of screen height
FORWARD_SPEED = -0.5      # Fixed forward speed (Negative is Forward in your robot)
STEERING_SENSITIVITY = 0.6 # 1.0 = Aggressive, 0.3 = Gentle

while cap.isOpened():
    success, frame = cap.read()
    if not success: break

    height, width, _ = frame.shape
    center_x, center_y = width // 2, height // 2
    
    # Default: Stop (0 speed, 0 turn)
    turn_val = 0.0
    speed_val = 0.0
    command_text = "SEARCHING"
    color = (0, 0, 255) # Red

    results = model.track(frame, persist=True, verbose=False)
    annotated_frame = frame.copy()

    if results[0].boxes.id is not None:
        # Extract data
        boxes = results[0].boxes.xyxy.cpu().numpy()
        track_ids = results[0].boxes.id.int().cpu().numpy()
        class_ids = results[0].boxes.cls.int().cpu().numpy()

        for box, track_id, cls in zip(boxes, track_ids, class_ids):
            if int(cls) != TARGET_CLASS_ID: continue

            x1, y1, x2, y2 = box
            obj_center_x = int((x1 + x2) / 2)
            obj_center_y = int((y1 + y2) / 2)
            
            # 1. CALCULATE PIXEL COVERAGE (DISTANCE)
            obj_height = y2 - y1
            pixel_coverage = obj_height / height

            # 2. CALCULATE SMOOTH STEERING (PROPORTIONAL)
            # Result is between -1.0 (Left Edge) and 1.0 (Right Edge)
            raw_turn_error = (obj_center_x - center_x) / (width / 2)
            
            # Apply sensitivity (Gain)
            turn_val = raw_turn_error * STEERING_SENSITIVITY
            
            # Clamp value just in case (keep between -1 and 1)
            turn_val = max(-1.0, min(1.0, turn_val))

            # 3. DETERMINE SPEED
            if pixel_coverage > STOP_DISTANCE:
                speed_val = 0.0
                turn_val = 0.0  # Stop turning if we arrived
                command_text = "STOP (Arrived)"
                color = (0, 0, 255)
            else:
                speed_val = FORWARD_SPEED
                command_text = f"TRACKING ({turn_val:.2f}, {speed_val})"
                color = (0, 255, 0)

            # --- VISUALS ---
            cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 4)
            cv2.line(annotated_frame, (center_x, center_y), (obj_center_x, obj_center_y), color, 2)
            cv2.putText(annotated_frame, command_text, (int(x1), int(y1)-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # --- OUTPUT FOR ROBOT ---
            # This print mimics your DIR command format: DIR <x_turn> <y_speed>
            # In your LiveFeed.py, Forward is Negative Y.
            print(f"CMD: DIR {turn_val:.3f} {speed_val:.3f}")
            
            break 

    cv2.imshow("Proportional Control", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord("q"): break

cap.release()
cv2.destroyAllWindows()