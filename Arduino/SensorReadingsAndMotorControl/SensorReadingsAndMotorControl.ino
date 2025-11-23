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

int   maxPWM          = 180;   // Default speed (0–255)
float deadzone        = 0.01;  // Ignore tiny throttle noise
float rudderDeadzone  = 0.02;  // Ignore tiny rudder noise
Servo rudder;

// ===================================
// === SENSOR PIN DEFINITIONS ===
// ===================================
#define TEMP_SENSOR_1 2   // DS18B20 1 (Water Temp/TDS ref)
#define TEMP_SENSOR_2 3   // DS18B20 2 (Air Temp)
#define PH_SENSOR     A0  // Analog pH sensor
#define TDS_SENSOR    A7  // Analog TDS sensor

// ===================================
// === SHARED SENSOR VARIABLES ===
// ===================================
const float VREF = 5.0;      // Vref for all analog

// Temp & TDS setup
OneWire oneWire1(TEMP_SENSOR_1);
OneWire oneWire2(TEMP_SENSOR_2);
DallasTemperature TempSensor1(&oneWire1);
DallasTemperature TempSensor2(&oneWire2);

#define SCOUNT 125       // Number of TDS samples (~5s @ 40ms/sample)
int   tdsAnalogBuffer[SCOUNT];
int   tdsAnalogBufferTemp[SCOUNT];
int   tdsAnalogBufferIndex = 0;
int   tdsSamplesFilled     = 0;
float tdsAverageVoltage    = 0.0;
float tdsValue             = 0.0;
float tempC1               = 0.0; // Water temperature
float tempC2               = 0.0; // Air temperature

// Accelerometer setup
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

// ===================================
// === pH Sensor Variables ===
// ===================================
const float PH_SLOPE     = -4.4615;   // m
const float PH_INTERCEPT = 13.2077;   // b
const float PH_OFFSET    = -0.7;      // extra offset
int   phRaw;
float phVoltage;
float pH = 0.0;

long  phSum            = 0;
const int PH_N         = 10;
int   phSampleCount    = 0;

// ===================================
// === TIMING CONSTANTS ===
// ===================================
const unsigned long TDS_SAMPLE_INTERVAL_MS   = 40UL;    // ms
const unsigned long PH_SAMPLE_INTERVAL_MS    = 20UL;    // ms
const unsigned long REPORT_INTERVAL_MS       = 5000UL;  // 5 s
const unsigned long TEMP_CONV_TIME_MS        = 750UL;   // DS18B20 max conv time

// Timing trackers
unsigned long lastTDSSampleMs    = 0;
unsigned long lastPhSampleMs     = 0;
unsigned long lastReportMs       = 0;
unsigned long lastTempConvStart  = 0;

// ===================================
// === TDS Median Filtering Function ===
// ===================================
int getMedianNum(int bArray[], int iFilterLen) {
  int bTab[SCOUNT];
  if (iFilterLen > SCOUNT) iFilterLen = SCOUNT;

  for (int i = 0; i < iFilterLen; i++) {
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

  if (iFilterLen <= 0) return 0;

  if (iFilterLen & 0x01) {
    return bTab[(iFilterLen - 1) / 2];
  } else {
    return (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
  }
}

// === Motor Stop ===
void stopMotor() {
  analogWrite(RPWM, 0);
  analogWrite(LPWM, 0);
}

// === Motor Drive Function (x = throttle, y = rudder) ===
void driveSingleMotor(float x, float y) {
  // Throttle
  if (fabs(x) < deadzone) x = 0;
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

  // Rudder
  if (fabs(y) < rudderDeadzone) y = 0;
  int angle = map((int)(y * 100.0f), -100, 100, 45, 135);
  angle = constrain(angle, 45, 135);
  rudder.write(angle);
}

// =================================================================
// 🚀 SETUP
// =================================================================
void setup() {
  Serial.begin(9600);

  // Motor & Servo
  pinMode(RPWM, OUTPUT);
  pinMode(LPWM, OUTPUT);
  pinMode(R_EN, OUTPUT);
  pinMode(L_EN, OUTPUT);
  digitalWrite(R_EN, HIGH);
  digitalWrite(L_EN, HIGH);
  stopMotor();

  rudder.attach(SERVO_PIN);
  rudder.write(90);  // center

  // Sensors
  pinMode(TDS_SENSOR, INPUT);
  pinMode(PH_SENSOR, INPUT);

  TempSensor1.begin();
  TempSensor2.begin();
  // Non-blocking conversion mode
  TempSensor1.setWaitForConversion(false);
  TempSensor2.setWaitForConversion(false);

  // Start first temperature conversion
  TempSensor1.requestTemperatures();
  TempSensor2.requestTemperatures();
  lastTempConvStart = millis();

  // Accelerometer
  Wire.begin();
  if (!accel.begin()) {
    Serial.println("No ADXL345 detected!");
    while (1);
  }
  accel.setRange(ADXL345_RANGE_2_G);

  // Timing
  unsigned long now = millis();
  lastTDSSampleMs = now;
  lastPhSampleMs  = now;
  lastReportMs    = now;

  // (Optional) comment this out if you don't want motor auto-test
  /*
  Serial.println("Arduino ready (motor + sensor mode)");
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
  */
}

// =================================================================
// ♾️ LOOP
// =================================================================
void loop() {
  unsigned long now = millis();

  // ---- Non-blocking DS18B20 handling ----
  if (now - lastTempConvStart >= TEMP_CONV_TIME_MS) {
    // Read conversion results
    tempC1 = TempSensor1.getTempCByIndex(0);
    tempC2 = TempSensor2.getTempCByIndex(0);

    // Start new conversion (non-blocking)
    TempSensor1.requestTemperatures();
    TempSensor2.requestTemperatures();
    lastTempConvStart = now;
  }

  // ---- 1. TDS sampling every 40 ms ----
  if (now - lastTDSSampleMs >= TDS_SAMPLE_INTERVAL_MS) {
    lastTDSSampleMs = now;

    int adc = analogRead(TDS_SENSOR);
    tdsAnalogBuffer[tdsAnalogBufferIndex] = adc;
    tdsAnalogBufferIndex++;
    if (tdsAnalogBufferIndex >= SCOUNT) {
      tdsAnalogBufferIndex = 0;
    }
    if (tdsSamplesFilled < SCOUNT) {
      tdsSamplesFilled++;
    }
  }

  // ---- 2. pH sampling every 20 ms (simple averaging) ----
  if (now - lastPhSampleMs >= PH_SAMPLE_INTERVAL_MS) {
    lastPhSampleMs = now;

    if (phSampleCount < PH_N) {
      phSum += analogRead(PH_SENSOR);
      phSampleCount++;
    }
  }

  // ---- 3. Reporting every 5 s ----
  if (now - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = now;

    // --- pH calculation ---
    if (phSampleCount > 0) {
      phRaw = phSum / phSampleCount;
    } else {
      phRaw = analogRead(PH_SENSOR);
    }
    phVoltage = phRaw * (VREF / 1023.0);
    float pH_raw = PH_SLOPE * phVoltage + PH_INTERCEPT;
    pH = pH_raw + PH_OFFSET;

    phSum = 0;
    phSampleCount = 0;

    // --- TDS calculation ---
    int nSamples = (tdsSamplesFilled > 0) ? tdsSamplesFilled : 1;
    for (int i = 0; i < nSamples; i++) {
      tdsAnalogBufferTemp[i] = tdsAnalogBuffer[i];
    }
    int medianAdc = getMedianNum(tdsAnalogBufferTemp, nSamples);
    tdsAverageVoltage = medianAdc * (float)VREF / 1024.0;

    float compensationCoefficient = 1.0 + 0.02 * (tempC1 - 25.0);
    float compensationVoltage     = tdsAverageVoltage / compensationCoefficient;
    tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage
                - 255.86 * compensationVoltage * compensationVoltage
                + 857.39 * compensationVoltage) * 0.5;

    // --- Accelerometer reading ---
    sensors_event_t event;
    accel.getEvent(&event);

    float ax = event.acceleration.x;
    float ay = event.acceleration.y;
    float az = event.acceleration.z;

    float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
    float roll  = atan2(ay, az) * 180.0 / PI;

    const char* orientation;
    if (az < -0.5)      orientation = "Upside Down";
    else if (az > 6.0)  orientation = "Upright";
    else                orientation = "Tilted";

    // --- Single-line DATA output ---
    Serial.print("DATA:");
    Serial.print("T1=");    Serial.print(tempC1, 2);
    Serial.print(",T2=");   Serial.print(tempC2, 2);
    Serial.print(",TDS=");  Serial.print(tdsValue, 0);
    Serial.print(",pH=");   Serial.print(pH, 2);
    Serial.print(",Pitch=");Serial.print(pitch, 2);
    Serial.print(",Roll="); Serial.print(roll, 2);
    Serial.print(",Orient="); Serial.print(orientation);
    Serial.println();
  }

  // ---- 4. Motor/Rudder Serial Control ----
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line.startsWith("DIR")) {
      line.remove(0, 3);
      line.trim();

      int spaceIndex = line.indexOf(' ');
      if (spaceIndex > 0) {
        String xs = line.substring(0, spaceIndex);
        String ys = line.substring(spaceIndex + 1);

        float x = xs.toFloat();   // throttle
        float y = ys.toFloat();   // rudder
        driveSingleMotor(x, y);
      }
    } else if (line.startsWith("SPEED")) {
      int val;
      if (sscanf(line.c_str(), "SPEED %d", &val) == 1) {
        maxPWM = map(val, 0, 100, 0, 255);
      }
    }
    // Ignore unknown lines
  }
}
