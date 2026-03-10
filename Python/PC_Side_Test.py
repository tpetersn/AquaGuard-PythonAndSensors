import imagezmq
import json

def main():
    image_hub = imagezmq.ImageHub()
    print("🧠 Laptop Minimal Brain Listening on Port 5555...")
    print("Waiting for Pi to connect...")

    try:
        while True:
            msg_str, image = image_hub.recv_jpg()
            
            # ✅ 修改点 1：分别获取三个方向的数据
            try:
                sonar_data = json.loads(msg_str)
                front_dist = sonar_data.get("front", 200.0)
                left_dist = sonar_data.get("left", 200.0)
                right_dist = sonar_data.get("right", 200.0)
            except json.JSONDecodeError:
                front_dist, left_dist, right_dist = 200.0, 200.0, 200.0
                print("⚠️ Invalid JSON received")

            # ✅ 修改点 2：极简三向决策逻辑
            if front_dist < 40.0:
                cmd = "DIR 0.0 0.0"       # 停
                action = "🛑 STOP"
            elif left_dist < 40.0:
                cmd = "DIR 0.0 0.6"       # 左侧有障碍，向右原地转 (throttle=0, turn=0.6)
                action = "↪️ TURN RIGHT"
            elif right_dist < 40.0:
                cmd = "DIR 0.0 -0.6"      # 右侧有障碍，向左原地转 (throttle=0, turn=-0.6)
                action = "↩️ TURN LEFT"
            else:
                cmd = "DIR 0.4 0.0"       # 前进
                action = "🟢 FORWARD"

            image_hub.send_reply(cmd.encode("utf-8"))
            
            # ✅ 修改点 3：把三个数值同时打印在屏幕上，方便你用手去挡着测！
            print(f"📡 Sonar [F:{front_dist:5.1f} L:{left_dist:5.1f} R:{right_dist:5.1f}] --> {action} (Sent: {cmd})")

    except KeyboardInterrupt:
        print("\nShutting down Laptop Brain...")

if __name__ == "__main__":
    main()