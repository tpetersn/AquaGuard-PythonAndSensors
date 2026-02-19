import pigpio
import time

pi = pigpio.pi()

TEST_PIN = 18   # use one of your PWM pins

pi.set_mode(TEST_PIN, pigpio.OUTPUT)
pi.set_PWM_frequency(TEST_PIN, 20000)

print("PWM ON")
pi.set_PWM_dutycycle(TEST_PIN, 128)  # 50%

time.sleep(3)

print("PWM OFF")
pi.set_PWM_dutycycle(TEST_PIN, 0)
pi.stop()