// === Libraries ===
#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <math.h>

// ===================================
// === MOTOR & SERVO DEFINITIONS ===
// ===================================
const int RPWM = 5;      // PWM forward
const int LPWM = 6;      // PWM reverse
const int R_EN = 4;
const int L_EN = 7;
const int SERVO_PIN = 9;

int maxPWM = 180;        // Default speed (0–255)
float deadzone = 0.01;   // Ignore tiny throttle noise
float rudderDeadzone = 0.02; // Ignore tiny rudder noise
Servo rudder;

// ===================================
// === SENSOR PIN DEFINITIONS ===
// Note: TDS moved to A1 to avoid conflict with pH (A0)
// ===================================
#define TEMP_SENSOR_1 2   // DS18B20 1 (Water Temp/TDS ref)
#define TEMP_SENSOR_2 3   // DS18B20 2 (Air Temp)
#define PH_SENSOR     A0  // Analog pH sensor
#define TDS_SENSOR    A7  // Analog TDS sensor

// ===================================
// === SHARED SENSOR VARIABLES ===
// ===================================
// VREF for all analog sensors
const float VREF = 5.0;      

// Temp & TDS setup
OneWire oneWire1(TEMP_SENSOR_1);
OneWire oneWire2(TEMP_SENSOR_2);
DallasTemperature TempSensor1(&oneWire1);
DallasTemperature TempSensor2(&oneWire2);

#define SCOUNT 125       // Number of samples (approx 5s @ 40ms/sample)
int   tdsAnalogBuffer[SCOUNT];
int   tdsAnalogBufferTemp[SCOUNT];
int   tdsAnalogBufferIndex = 0;
float tdsAverageVoltage = 0.0;
float tdsValue          = 0.0;
float tempC1 = 0.0; // Water temperature
float tempC2 = 0.0; // Air temperature

// Accelerometer setup
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

// ===================================
// === pH Sensor Variables (Calibration Preserved) ===
// ===================================
const float PH_SLOPE     = -4.4615;   // m
const float PH_INTERCEPT = 13.2077;   // b
const float PH_OFFSET    = -0.7;      // Quick fix offset (as per your code)
int   phRaw; // Raw ADC reading for pH
float phVoltage;
float pH = 0.0;

// pH sampling variables for non-blocking averaging
long phSum = 0;
const int PH_N = 10;
int phSampleCount = 0;
unsigned long phSampleTimepoint = 0; // used for 20ms pH sampling

// ===================================
// === TIMING VARIABLES ===
// ===================================
unsigned long tdsSampleTimepoint = 0; // Used for 40 ms TDS sampling
unsigned long printTimepoint     = 0; // Used for 5 s sensor reporting

// ===================================
// === TDS Median Filtering Function ===
// (Unmodified from your sensor code)
// ===================================
int getMedianNum(int bArray[], int iFilterLen) {
    int bTab[SCOUNT];
    for (byte i = 0; i < iFilterLen; i++) {
        bTab[i] = bArray[i];
    }
    for (int j = 0; j < iFilterLen - 1; j++) {
        for (int i = 0; i < iFilterLen - j - 1; i++) {
            if (bTab[i] > bTab[i + 1]) {
                int bTemp = bTab[i];
                bTab[i] = bTab[i + 1];
                bTab[i + 1] = bTemp;
            }
        }
    }
    if ((iFilterLen & 1) > 0) {
        return bTab[(iFilterLen - 1) / 2];
    } else {
        return (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
    }
}

// === Temperature Reading Function ===
float readTempC(DallasTemperature &sensor) {
    sensor.requestTemperatures();
    return sensor.getTempCByIndex(0);
}

// === Motor Stop Function ===
void stopMotor() {
    analogWrite(RPWM, 0);
    analogWrite(LPWM, 0);
}

// === Motor Drive Function (X=throttle, Y=rudder) ===
void driveSingleMotor(float x, float y) {
    // Throttle control (X)
    if (abs(x) < deadzone) x = 0;
    int pwmValue = maxPWM;

    if (x > 0) {
        analogWrite(LPWM, 0);
        analogWrite(RPWM, pwmValue);
    } else if (x < 0) {
        analogWrite(RPWM, 0);
        analogWrite(LPWM, pwmValue);
    } else {
        stopMotor();
    }

    // Rudder control (Y)
    if (abs(y) < rudderDeadzone) y = 0;
    int angle = map(y * 100, -100, 100, 45, 135);
    angle = constrain(angle, 45, 135);
    rudder.write(angle);

    Serial.print("Rudder angle = ");
    Serial.println(angle);
}

// =================================================================
// 🚀 SETUP
// =================================================================
void setup() {
    // Set Baud rate to 9600 to match the Python script
    Serial.begin(9600);

    // --- Motor & Servo Setup ---
    pinMode(RPWM, OUTPUT);
    pinMode(LPWM, OUTPUT);
    pinMode(R_EN, OUTPUT);
    pinMode(L_EN, OUTPUT);
    digitalWrite(R_EN, HIGH);
    digitalWrite(L_EN, HIGH);
    stopMotor();
    rudder.attach(SERVO_PIN);
    rudder.write(90);  // center

    // --- Sensor Pin Setup ---
    pinMode(TDS_SENSOR, INPUT);
    pinMode(PH_SENSOR, INPUT);
    TempSensor1.begin();
    TempSensor2.begin();

    // --- Accelerometer Setup ---
    Wire.begin();
    if (!accel.begin()) {
        Serial.println("No ADXL345 detected!");
        while (1); // stop here if not found
    }
    accel.setRange(ADXL345_RANGE_2_G);

    // --- Initialize Timers ---
    unsigned long now = millis();
    tdsSampleTimepoint = now;
    printTimepoint     = now;
    phSampleTimepoint  = now;

    Serial.println("Arduino ready (motor + sensor mode)");

    // --- Auto-Test (kept from original motor code) ---
    Serial.println("Starting motor auto-test...");
    int testSpeeds[3] = {85, 170, 255};
    for (int i = 0; i < 3; i++) {
        int pwm = testSpeeds[i];
        Serial.print("Testing speed PWM = ");
        Serial.println(pwm);
        analogWrite(LPWM, 0);
        analogWrite(RPWM, pwm);
        delay(1500);
        stopMotor();
        delay(700);
    }
    Serial.println("Motor auto-test complete.");
}

// =================================================================
// ♾️ LOOP
// =================================================================

//this for the time for sampling and sending readings
const unsigned long SENSOR_PERIOD_MS = 15000UL;  // 15 seconds (adjust as needed)


void loop() {
    unsigned long now = millis();

    // --- 1. Non-blocking TDS Sampling (every 40ms) ---
    if (now - tdsSampleTimepoint >= SENSOR_PERIOD_MS) {
        tdsSampleTimepoint += SENSOR_PERIOD_MS;
        tdsAnalogBuffer[tdsAnalogBufferIndex] = analogRead(TDS_SENSOR);
        tdsAnalogBufferIndex++;
        if (tdsAnalogBufferIndex == SCOUNT) {
            tdsAnalogBufferIndex = 0;
        }
    }

    // --- 2. Non-blocking pH Sampling (every 20ms, for 10 samples) ---
    // This simulates the original delay(20) * 10 samples for averaging


    if (now - phSampleTimepoint >= SENSOR_PERIOD_MS) {
        phSampleTimepoint += SENSOR_PERIOD_MS;
        if (phSampleCount < PH_N) {
            phSum += analogRead(PH_SENSOR);
            phSampleCount++;
        }
    }


    // --- 3. 5-Second Sensor Reading & Reporting ---
    if (now - printTimepoint >= SENSOR_PERIOD_MS) {
        printTimepoint += SENSOR_PERIOD_MS;

        // --- pH Calculation (uses accumulated sum from samples) ---
        if (phSampleCount == PH_N) {
            phRaw = phSum / PH_N;
            phVoltage = phRaw * (VREF / 1023.0);
            float pH_raw = PH_SLOPE * phVoltage + PH_INTERCEPT;
            pH = pH_raw + PH_OFFSET;
            // Reset for next 5-second cycle
            phSum = 0;
            phSampleCount = 0;
        }
        // Force an analog read if the sampling wasn't completed (shouldn't happen)
        else {
             phRaw = analogRead(PH_SENSOR);
             phVoltage = phRaw * (VREF / 1023.0);
             float pH_raw = PH_SLOPE * phVoltage + PH_INTERCEPT;
             pH = pH_raw + PH_OFFSET;
             phSum = 0;
             phSampleCount = 0;
        }

        // --- TDS Calculation ---
        for (int copyIndex = 0; copyIndex < SCOUNT; copyIndex++) {
            tdsAnalogBufferTemp[copyIndex] = tdsAnalogBuffer[copyIndex];
        }
        tdsAverageVoltage = getMedianNum(tdsAnalogBufferTemp, SCOUNT) * (float)VREF / 1024.0;

        // --- Temperature Reading ---
        tempC1 = readTempC(TempSensor1); // Water temp (for TDS compensation)
        tempC2 = readTempC(TempSensor2); // Air temp

        // TDS Compensation
        float compensationCoefficient = 1.0 + 0.02 * (tempC1 - 25.0);
        float compensationVoltage     = tdsAverageVoltage / compensationCoefficient;
        tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage
                   - 255.86 * compensationVoltage * compensationVoltage
                   + 857.39 * compensationVoltage) * 0.5;

        // --- Accelerometer Reading ---
        sensors_event_t event;
        accel.getEvent(&event);

        // Raw acceleration values (m/s^2 with Adafruit library)
        float ax = event.acceleration.x;
        float ay = event.acceleration.y;
        float az = event.acceleration.z;

        // --- Compute Pitch, Roll, and Tilt ---
        // Pitch: forward/back tilt
        float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;

        // Roll: left/right tilt
        float roll  = atan2(ay, az) * 180.0 / PI;

        // Total Tilt angle from "upright" (angle between Z-axis and gravity vector)
        float norm = sqrt(ax * ax + ay * ay + az * az);
        if (norm == 0) norm = 1;  // avoid division by zero
        float tilt = acos(az / norm) * 180.0 / PI;

        // Orientation label (keep your old logic so nothing breaks)
        const char* orientation;
        if (az < -0.5)      orientation = "Upside Down";
        else if (az > 6.0)  orientation = "Upright";
        else                orientation = "Tilted";

        // --- Output Sensor Data for Python Gateway ---
        // Example:
        // DATA:T1=25.50,T2=22.30,TDS=350,pH=7.21,AccelZ=-9.81,Pitch=12.34,Roll=-3.21,Tilt=15.67,Orient=Upright


        Serial.print("DATA:");
        Serial.print("T1="); Serial.print(tempC1, 2);
        Serial.print(",T2="); Serial.print(tempC2, 2);
        Serial.print(",TDS="); Serial.print(tdsValue, 0);
        Serial.print(",pH=");  Serial.print(pH, 2);
        Serial.print(",Orient="); Serial.println(orientation);
        Serial.print(",Pitch="); Serial.println(pitch);
        Serial.print(",Roll="); Serial.println(roll);
        





        

    }

    // --- 4. Motor/Rudder Serial Control ---
    if (Serial.available()) {
        String line = Serial.readStringUntil('\n');
        line.trim();

        if (line.startsWith("DIR")) {
            // ... (motor control logic remains the same)
            line.remove(0, 3);
            line.trim();

            int spaceIndex = line.indexOf(' ');
            if (spaceIndex > 0) {
                String xs = line.substring(0, spaceIndex);
                String ys = line.substring(spaceIndex + 1);

                float x = xs.toFloat();   // throttle
                float y = ys.toFloat();   // rudder

                // Serial.print("Parsed throttle x = ");
                // Serial.println(x);
                // Serial.print("Parsed rudder y   = ");
                // Serial.println(y);

                driveSingleMotor(x, y);
            }
        } else if (line.startsWith("SPEED")) {
            // ... (speed control logic remains the same)
            int val;
            if (sscanf(line.c_str(), "SPEED %d", &val) == 1) {
                maxPWM = map(val, 0, 100, 0, 255);
                // Serial.print("Max speed set to: ");
                // Serial.println(maxPWM);
            }
        }
        // Ignore lines that are not DIR or SPEED (like the sensor DATA line)
    }
}
