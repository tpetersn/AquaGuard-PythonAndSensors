import serial
import time

PORT = "COM6"
BAUD_RATE = 9600

try:
    port = serial.Serial(PORT, BAUD_RATE, timeout=2)
    time.sleep(2)  # wait for Arduino reset after connection
    print(f"Connected to {PORT}. Reading sonar sensor... (Ctrl+C to stop)\n")

    while True:
        line = port.readline().decode("utf-8", errors="replace").strip()
        if line:
            print(line)

except serial.SerialException as e:
    print(f"Serial error: {e}")
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    if "port" in locals() and port.is_open:
        port.close()
        print("Port closed.")
