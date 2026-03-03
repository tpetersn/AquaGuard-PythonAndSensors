# JSNR04T-2.0 Ultrasonic Sonar Sensor Test
# Trig = GPIO 7, Echo = GPIO 6

import RPi.GPIO as GPIO
import time

TRIG_PIN = 7
ECHO_PIN = 6

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)
GPIO.output(TRIG_PIN, GPIO.LOW)

time.sleep(1)  # JSNR04T needs ~500ms power-on stabilization
print("JSNR04T-2.0 sonar test ready")
print(f"Echo pin state: {GPIO.input(ECHO_PIN)}")

try:
    while True:
        # Send 20us trigger pulse (JSNR04T may need longer than 10us)
        GPIO.output(TRIG_PIN, GPIO.LOW)
        time.sleep(0.000005)
        GPIO.output(TRIG_PIN, GPIO.HIGH)
        time.sleep(0.00002)
        GPIO.output(TRIG_PIN, GPIO.LOW)

        # Read echo pulse duration (timeout 60ms for JSNR04T's longer range)
        timeout = 0.06
        start_time = time.time()

        # Wait for echo pin to go HIGH
        while GPIO.input(ECHO_PIN) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > timeout:
                pulse_start = None
                break

        if pulse_start is None:
            print(f"No echo (pin={GPIO.input(ECHO_PIN)}) - check wiring: VCC=5V, Trig=GPIO7, Echo=GPIO6")
        else:
            # Wait for echo pin to go LOW
            while GPIO.input(ECHO_PIN) == 1:
                pulse_end = time.time()
                if pulse_end - start_time > timeout:
                    pulse_end = None
                    break

            if pulse_end is None:
                print(f"No echo (pin={GPIO.input(ECHO_PIN)}) - check wiring: VCC=5V, Trig=GPIO7, Echo=GPIO6")
            else:
                duration_us = (pulse_end - pulse_start) * 1_000_000
                distance_cm = duration_us * 0.0343 / 2.0
                print(f"Distance: {distance_cm:.1f} cm  (raw={int(duration_us)} us)")

        time.sleep(0.6)  # JSNR04T needs at least 200ms between measurements

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    GPIO.cleanup()
