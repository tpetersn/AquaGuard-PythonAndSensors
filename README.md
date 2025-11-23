🌊 PoolBot Controller (Arduino, Python Gateway, LiveKit Bridge)

This project integrates motor control and five environmental sensors on an Arduino Nano/Uno with a Python gateway running on a host computer (e.g., Raspberry Pi). This gateway handles two critical functions simultaneously:

Real-Time Control: Receiving motor commands via LiveKit (WebRTC) and sending them to the Arduino.

Sensor Telemetry: Reading structured sensor data from the Arduino and posting it to an external backend service using SendReadings.post_reading.

💾 Project Files

File

Description

mega_controller.ino

The unified Arduino sketch for motor control, servo, 2x temperature, TDS, pH, and accelerometer.

robot_gateway.py

The asynchronous Python script that bridges LiveKit, the Arduino serial port, and the external API.

SendReadings.py

(External) Module containing the post_reading function for sending data to the backend.

1. Arduino Hardware and Wiring

The Arduino sketch uses a non-blocking architecture (based on millis()) to ensure motor commands are processed instantly, even while gathering and averaging sensor data over 5-second intervals.

📌 Pin Assignments

Component

Arduino Pin

Type

Notes

Motor PWM Fwd (RPWM)

D5

Digital OUT



Motor PWM Rev (LPWM)

D6

Digital OUT



Motor Enable (R_EN/L_EN)

D7, D8

Digital OUT

Set HIGH for continuous operation

Rudder Servo

D9

Digital OUT

Controls steering (mapped 45° to 135°)

Water Temp (DS18B20)

D2

Digital IN/OUT

Used for TDS temperature compensation

Air Temp (DS18B20)

D3

Digital IN/OUT



pH Sensor

A0

Analog IN

CRITICAL: Uses custom calibration constants.

TDS Sensor

A1

Analog IN

(Moved from A0 to resolve conflict)

Accelerometer (ADXL345)

A4, A5

I2C (SDA, SCL)

Requires the Wire.h library

⚙️ Calibration Data (pH Sensor)

The pH sensor calculations rely heavily on the constants below, which are included and preserved in mega_controller.ino:

const float VREF = 4.90;
const float PH_SLOPE     = -4.4615;
const float PH_INTERCEPT = 13.2077;
const float PH_OFFSET    = -0.7; // Quick fix offset


2. Arduino Serial Communication Protocol

The Arduino uses a 9600 baud rate and communicates in two distinct ways:

A. Telemetry Output (Arduino → Python)

Every 5 seconds, the Arduino sends a single line of structured, comma-separated data, prefixed with DATA:, which the Python script parses using a regular expression.

Field

Description

T1

Water Temperature (°C)

T2

Air Temperature (°C)

TDS

Total Dissolved Solids (ppm)

pH

Calibrated pH value

AccelZ

Z-axis acceleration (m/s²)

Orient

Board orientation (Upright, Tilted, Upside Down)

Example Output Line:
DATA:T1=25.50,T2=22.30,TDS=350,pH=7.21,AccelZ=-9.81,Orient=Upright

B. Motor Control Input (Python → Arduino)

The Arduino listens for control commands sent from the Python gateway (which originates from LiveKit).

Command Format

Example

Action

DIR <X> <Y>

DIR 1.000 0.000

Analog control: X (Throttle: -1 reverse, +1 forward), Y (Rudder: -1 right, +1 left).

SPEED <percent>

SPEED 75

Sets maxPWM (0-255) based on a 0-100% value.

3. Python Gateway Setup (robot_gateway.py)

The Python gateway is the central hub, managing asynchronous connections.

🐍 Dependencies

You must install these libraries on the host computer (e.g., Raspberry Pi):

pip install pyserial requests livekit opencv-python


⚙️ Gateway Configuration

Before running, update the configuration constants in robot_gateway.py:

# --- LiveKit Config ---
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "[https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool](https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool)"

# --- Arduino Serial Config ---
ARDUINO_PORT = "COM3"           # <-- UPDATE THIS (e.g., /dev/ttyACM0 on Linux)
BAUD = 9600                     # Must be 9600

# --- External Service Config ---
DEVICE_ID = "68cc90c7ef0763dddf1a5e9d" # <-- UPDATE THIS (Your actual device ID)


🧠 Logic Flow

The gateway runs three concurrent tasks using asyncio:

main() / LiveKit Connection: Connects to the LiveKit room, publishes the camera track, and sets up a listener (on_data_received) for incoming remote control commands (DIR, SPEED).

CameraStream.run(): Continuously captures video from the attached webcam (cv2.VideoCapture(0)) and pushes the frames to LiveKit.

sensor_reader_task(): Runs in a separate thread to handle the blocking serial communication. It checks arduino.in_waiting, parses the DATA: line, and calls post_reading() with the extracted sensor values.




🚀 Execution

The script is started using asyncio:

python robot_gateway.py


The console output will show successful LiveKit connection, confirmation of the sensor reader task starting, sent motor commands, and successful sensor data posts.
