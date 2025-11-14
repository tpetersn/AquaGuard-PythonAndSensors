import serial
import re
import time
from SendReadings import post_reading

if __name__ == '__main__':
    # Set up the serial connection to your Arduino
    ser = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    ser.reset_input_buffer()

    device_id = "68cc90c7ef0763dddf1a5e9d"  # Replace with your actual device ID

    print("📡 Listening for temperature readings...")

    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()

                # Example incoming line: "Temp: 22C"
                match = re.search(r"Temp:\s*([\d.]+)", line)
                if match:
                    temperature = float(match.group(1))
                    print(f"🌡️ Received temperature: {temperature}°C")

                    # Arbitrary values for other fields
                    ph = 7.2
                    chlorine = 1.1
                    tds = 350
                    battery_voltage = 3.7
                    battery_percentage = 85

                    # Post the reading
                    response = post_reading(
                        device_id,
                        temperature=temperature,
                        ph=ph,
                        chlorine=chlorine,
                        tds=tds,
                        battery_voltage=battery_voltage,
                        battery_percentage=battery_percentage
                    )

                    print("✅ Reading sent successfully:", response)

                else:
                    print("⚠️ Unrecognized line:", line)

            time.sleep(0.5)

        except Exception as e:
            print("❌ Error:", e)
            time.sleep(2)
