import imagezmq
import serial
import json
import time
import pigpio
import cv2
import numpy as np

# === CONFIGURATION ===
LAPTOP_IP = "192.168.1.XXX"  # ⚠️ 必须改成你电脑的 IP
ARDUINO_PORT = "/dev/ttyUSB1" # ⚠️ 确认 Arduino 的串口号
BAUD = 9600

# Motor GPIO (BCM)
L_FWD, L_REV, R_FWD, R_REV = 18, 19, 12, 13
MAX_PWM = 30  # 旱地测试，PWM设小一点防止电机乱飞

# === SETUP MOTORS ===
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("❌ pigpio daemon not running")

for pin in [L_FWD, L_REV, R_FWD, R_REV]:
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.set_PWM_frequency(pin, 20000)
    pi.set_PWM_dutycycle(pin, 0)

def set_motor(fwd, rev, value):
    pwm = int(abs(value) * MAX_PWM)
    if value > 0:
        pi.set_PWM_dutycycle(rev, 0); pi.set_PWM_dutycycle(fwd, pwm)
    elif value < 0:
        pi.set_PWM_dutycycle(fwd, 0); pi.set_PWM_dutycycle(rev, pwm)
    else:
        pi.set_PWM_dutycycle(fwd, 0); pi.set_PWM_dutycycle(rev, 0)

def drive_diff(throttle, turn):
    left = max(-1.0, min(1.0, throttle + turn))
    right = max(-1.0, min(1.0, throttle - turn))
    set_motor(L_FWD, L_REV, left)
    set_motor(R_FWD, R_REV, right)

# === SETUP ARDUINO ===
try:
    arduino = serial.Serial(ARDUINO_PORT, BAUD, timeout=0.1)
    time.sleep(2)
    arduino.reset_input_buffer()
    print(f"🔌 Arduino connected on {ARDUINO_PORT}")
except Exception as e:
    print(f"❌ Arduino Error: {e}")
    arduino = None

# === MAIN LOOP ===
def main():
    sender = imagezmq.ImageSender(connect_to=f"tcp://{LAPTOP_IP}:5555")
    print(f"🚀 Pi ready. Connecting to {LAPTOP_IP}...")
    
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    _, dummy_jpg = cv2.imencode(".jpg", dummy_frame)
    
    # ✅ 修改点 1：初始化三个方向的安全距离
    f_dist, l_dist, r_dist = 200.0, 200.0, 200.0 

    try:
        while True:
            # 1. 读取 Arduino 最新的一行数据
            if arduino and arduino.in_waiting > 0:
                try:
                    line = arduino.readline().decode("utf-8").strip()
                    # ✅ 修改点 2：解析以逗号分隔的三个数据
                    if line.startswith("SONAR:"):
                        parts = line.split(":")[1].split(",")
                        if len(parts) == 3:
                            f_dist = float(parts[0])
                            l_dist = float(parts[1])
                            r_dist = float(parts[2])
                except: pass

            # 2. ✅ 修改点 3：将三个数据打包进 JSON
            msg = json.dumps({"front": f_dist, "left": l_dist, "right": r_dist})
            
            try:
                reply_bytes = sender.send_jpg(msg, dummy_jpg)
                reply_str = reply_bytes.decode("utf-8")
                
                if reply_str.startswith("DIR"):
                    parts = reply_str.split()
                    throttle = float(parts[1])
                    turn = float(parts[2])
                    drive_diff(throttle, turn)
                    # print(f"<- Laptop says: {reply_str} | Motor running") # 测试时可解开注释看明细
                    
            except Exception as e:
                print(f"⚠️ Network error (Is Laptop script running?): {e}")
                drive_diff(0, 0)
                time.sleep(1)

            time.sleep(0.05) 

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        drive_diff(0, 0)
        pi.stop()

if __name__ == "__main__":
    main()