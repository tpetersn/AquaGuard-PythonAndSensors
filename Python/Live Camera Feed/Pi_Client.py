import cv2
import imagezmq
import socket
import time
import serial

# --- CONFIGURATION ---
# 1. LAPTOP IP ADDRESS
# CHANGE THIS to your Laptop's IPv4 Address (e.g., 192.168.1.15)
# The laptop must be running the 'Laptop_Brain.py' script first!
LAPTOP_IP = "192.168.1.XXX" 

# 2. ARDUINO SETTINGS
# On Raspberry Pi, Arduino is usually /dev/ttyACM0 or /dev/ttyUSB0
ARDUINO_PORT = "/dev/ttyACM0" 
BAUD_RATE = 9600

# --- SETUP ARDUINO CONNECTION ---
arduino = None

def init_arduino():
    global arduino
    try:
        # Try connecting to the specific port
        arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for Arduino to reset
        print(f"✅ Arduino connected on {ARDUINO_PORT}")
    except Exception as e:
        print(f"⚠️ Arduino not found on {ARDUINO_PORT}. Retrying in loop...")
        arduino = None

def send_cmd_to_arduino(cmd):
    """
    Sends the command string to Arduino.
    Expects commands like: "DIR 0.5 -0.2" or "STOP"
    """
    if arduino and arduino.is_open:
        try:
            # Arduino expects a newline character '\n' to know the message ended
            arduino.write((cmd + "\n").encode("utf-8"))
            print(f"🤖 Sent to Motor: {cmd}")
        except Exception as e:
            print(f"❌ Serial Write Error: {e}")
    else:
        print(f"🚫 (Simulated) Motor Command: {cmd} [Arduino Disconnected]")

# --- MAIN LOOP ---
def main():
    # 1. Connect to Laptop (The Brain)
    print(f"📡 Connecting to Laptop Brain at {LAPTOP_IP}:5555...")
    try:
        sender = imagezmq.ImageSender(connect_to=f"tcp://{LAPTOP_IP}:5555")
    except Exception as e:
        print(f"❌ Could not connect to Laptop: {e}")
        return

    # 2. Connect to Arduino (The Muscle)
    init_arduino()

    # 3. Setup Camera (The Eyes)
    cap = cv2.VideoCapture(0)
    # Lower resolution slightly for faster WiFi transmission (low latency)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Get Hostname for identification
    rpi_name = socket.gethostname()
    
    time.sleep(2.0) # Warmup camera
    print("🚀 Pi Client Started! Streaming video...")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("❌ Camera failed to read frame.")
                time.sleep(1)
                continue

            # A. COMPRESS FRAME
            # Sending raw video is too slow. Compress to JPEG (quality 60 is a good balance).
            ret_code, jpg_buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])

            # B. SEND & WAIT (The Sync Step)
            # This line sends the image AND blocks (pauses) until the Laptop replies.
            # The reply will be the command string (e.g., "DIR 0.4 0.1")
            reply_bytes = sender.send_jpg(rpi_name, jpg_buffer)
            
            # C. DECODE COMMAND
            command_str = reply_bytes.decode("utf-8")

            # D. EXECUTE COMMAND
            send_cmd_to_arduino(command_str)

    except KeyboardInterrupt:
        print("\n🛑 Stopping Pi Client...")
    except Exception as e:
        print(f"❌ Critical Error: {e}")
    finally:
        cap.release()
        if arduino:
            arduino.close()

if __name__ == "__main__":
    main()