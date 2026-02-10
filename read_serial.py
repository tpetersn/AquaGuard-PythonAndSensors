import serial
import time

port = serial.Serial("COM4", 9600, timeout=2)
time.sleep(2)  # wait for Arduino reset after connection

print("Reading sonar sensor output...")
for _ in range(15):
    line = port.readline().decode("utf-8", errors="replace").strip()
    if line:
        print(line)
    else:
        print("(timeout - no data)")

port.close()
print("--- Done ---")
