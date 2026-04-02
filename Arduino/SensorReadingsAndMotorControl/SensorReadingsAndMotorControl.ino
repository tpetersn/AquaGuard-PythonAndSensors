// === Libraries ===
#include <Servo.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <math.h>
#include <SoftwareSerial.h>



int   maxPWM          = 180;   // Default speed (0–255)
float deadzone        = 0.01;  // Ignore tiny throttle noise
float rudderDeadzone  = 0.02;  // Ignore tiny rudder noise
Servo rudder;

// ===================================
// === SENSOR PIN DEFINITIONS ===
#define TEMP_SENSOR_1 2   // DS18B20 1 (Water Temp/TDS ref)
#define TEMP_SENSOR_2 3   // DS18B20 2 (Air Temp)
#define PH_SENSOR     A0  // Analog pH sensor
#define TDS_SENSOR    A1  // Analog TDS sensor
const int TRIG_LEFT = 7;
const int ECHO_LEFT = 6;

const int TRIG_RIGHT = 5;
const int ECHO_RIGHT = 4;

const int TRIG_FRONT = 9;
const int ECHO_FRONT = 8;

// ===================================
// === SHARED SENSOR VARIABLES ===
const float VREF = 5.0;      // Vref for all analog

OneWire oneWire1(TEMP_SENSOR_1);
OneWire oneWire2(TEMP_SENSOR_2);
DallasTemperature TempSensor1(&oneWire1);
DallasTemperature TempSensor2(&oneWire2);

#define SCOUNT 125
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
bool accelAvailable = false;

// ===================================
// === pH Sensor Variables ===
const float PH_SLOPE     = -4.3333;
const float PH_INTERCEPT = 20.65;
const float PH_OFFSET    = -0.40;      
int   phRaw;
float phVoltage;
float pH = 0.0;

long  phSum            = 0;
const int PH_N         = 10;
int   phSampleCount    = 0;

// ===================================
// === TIMING CONSTANTS ===
const unsigned long TDS_SAMPLE_INTERVAL_MS   = 40UL;    
const unsigned long PH_SAMPLE_INTERVAL_MS    = 20UL;    
const unsigned long REPORT_INTERVAL_MS       = 200UL;  
const unsigned long TEMP_CONV_TIME_MS        = 750UL;  

// Timing trackers
unsigned long lastTDSSampleMs    = 0;
unsigned long lastPhSampleMs     = 0;
unsigned long lastReportMs       = 0;
unsigned long lastTempConvStart  = 0;

// ===================================
// === TDS Median Filtering Function ===
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





// =================================================================
// 🚀 SETUP
// =================================================================
void setup() {
  Serial.begin(9600);
  



  // Sensors
  pinMode(TDS_SENSOR, INPUT);
  pinMode(PH_SENSOR, INPUT);

  TempSensor1.begin();
  TempSensor2.begin();
  TempSensor1.setWaitForConversion(false);
  TempSensor2.setWaitForConversion(false);

  TempSensor1.requestTemperatures();
  TempSensor2.requestTemperatures();
  lastTempConvStart = millis();

  // Accelerometer
  Wire.begin();
  accelAvailable = accel.begin();
  if (!accelAvailable) {
    Serial.println("No ADXL345 detected — continuing without it");
  } else {
    accel.setRange(ADXL345_RANGE_2_G);
    Serial.println("ADXL345 initialized");
  }

  // Timing
  unsigned long now = millis();
  lastTDSSampleMs = now;
  lastPhSampleMs  = now;
  lastReportMs    = now;

  Serial.print("Temp1 devices: ");
  Serial.println(TempSensor1.getDeviceCount());

  Serial.print("Temp2 devices: ");
  Serial.println(TempSensor2.getDeviceCount());

  pinMode(TRIG_FRONT, OUTPUT); pinMode(ECHO_FRONT, INPUT);
  pinMode(TRIG_LEFT, OUTPUT);  pinMode(ECHO_LEFT, INPUT);
  pinMode(TRIG_RIGHT, OUTPUT); pinMode(ECHO_RIGHT, INPUT);
  
  // Ensure all triggers start LOW
  digitalWrite(TRIG_FRONT, LOW);
  digitalWrite(TRIG_LEFT, LOW);
  digitalWrite(TRIG_RIGHT, LOW);
  
  // 1s stabilization time for JSNR04T waterproof sensors
  delay(1000); 
  Serial.println("System Ready. Sequential Firing Initiated.");
}

float readSonar(int trigPin, int echoPin) {
  // Send a 20us HIGH pulse to trigger the sensor
  // (JSNR04T prefers 20us over the standard 10us for stability)
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(20);
  digitalWrite(trigPin, LOW);

  // pulseIn blocks until echo is received. 
  // 60000us (60ms) timeout prevents the Arduino from freezing if facing open water
  long duration = pulseIn(echoPin, HIGH, 60000);
  
  if (duration == 0) {
    // If timeout occurs (no echo returned), return a default safe distance of 200.0 cm
    return 200.0; 
  }
  
  // Convert duration to centimeters (Speed of sound is 343m/s)
  return (duration * 0.0343) / 2.0;
}

// =================================================================
// ♾️ LOOP
// =================================================================
void loop() {
  unsigned long now = millis();

  // ---- Sonar reading ----
  // --- SONAR ---
  float dist_front = readSonar(TRIG_FRONT, ECHO_FRONT);
  float dist_left  = readSonar(TRIG_LEFT, ECHO_LEFT);
  float dist_right = readSonar(TRIG_RIGHT, ECHO_RIGHT);

  

  if (now - lastTempConvStart >= TEMP_CONV_TIME_MS) {
      float request1 = TempSensor1.getTempCByIndex(0);
      float request2 = TempSensor2.getTempCByIndex(0);

      // Only update if the reading is valid (not -127)
      if (request1 > -100) tempC1 = request1;
      if (request2 > -100) tempC2 = request2;

      TempSensor1.requestTemperatures();
      TempSensor2.requestTemperatures();
      lastTempConvStart = now;
  }

  // ---- Non-blocking DS18B20 handling ----
  if (now - lastTempConvStart >= TEMP_CONV_TIME_MS) {
    tempC1 = TempSensor1.getTempCByIndex(0);
    tempC2 = TempSensor2.getTempCByIndex(0);
    TempSensor1.requestTemperatures();
    TempSensor2.requestTemperatures();
    lastTempConvStart = now;
  }

  // ---- TDS sampling ----
  if (now - lastTDSSampleMs >= TDS_SAMPLE_INTERVAL_MS) {
    lastTDSSampleMs = now;
    int adc = analogRead(TDS_SENSOR);
    tdsAnalogBuffer[tdsAnalogBufferIndex++] = adc;
    if (tdsAnalogBufferIndex >= SCOUNT) tdsAnalogBufferIndex = 0;
    if (tdsSamplesFilled < SCOUNT) tdsSamplesFilled++;
  }

  // ---- pH sampling ----
  if (now - lastPhSampleMs >= PH_SAMPLE_INTERVAL_MS) {
    lastPhSampleMs = now;
    if (phSampleCount < PH_N) {
      phSum += analogRead(PH_SENSOR);
      phSampleCount++;
    }
  }

  // ---- Reporting ----
  if (now - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = now;

    // pH calculation
    if (phSampleCount > 0) phRaw = phSum / phSampleCount;
    else phRaw = analogRead(PH_SENSOR);
    phVoltage = phRaw * (VREF / 1023.0);
    float pH_raw = PH_SLOPE * phVoltage + PH_INTERCEPT;
    pH = pH_raw + PH_OFFSET;
    phSum = 0; phSampleCount = 0;

    // TDS calculation
    int nSamples = (tdsSamplesFilled > 0) ? tdsSamplesFilled : 1;
    for (int i = 0; i < nSamples; i++) tdsAnalogBufferTemp[i] = tdsAnalogBuffer[i];
    int medianAdc = getMedianNum(tdsAnalogBufferTemp, nSamples);
    tdsAverageVoltage = medianAdc * (float)VREF / 1024.0;
    float compensationCoefficient = 1.0 + 0.02 * (tempC1 - 25.0);
    float compensationVoltage = tdsAverageVoltage / compensationCoefficient;
    tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage
                - 255.86 * compensationVoltage * compensationVoltage
                + 857.39 * compensationVoltage) * 0.5;

    // Accelerometer reading only if available
    float ax=-999, ay=-999, az=-999, pitch=-999, roll=-999;
    const char* orientation = "Unknown";

    if (accelAvailable) {
      sensors_event_t event;
      accel.getEvent(&event);
      ax = event.acceleration.x;
      ay = event.acceleration.y;
      az = event.acceleration.z;
      pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
      roll  = atan2(ay, az) * 180.0 / PI;
      if (az < -0.5) orientation = "Upside Down";
      else if (az > 6.0) orientation = "Upright";
      else orientation = "Tilted";
    }

    // Send DATA line
    Serial.print("DATA:");
    Serial.print("T1="); Serial.print(tempC1, 2);
    Serial.print(",T2="); Serial.print(tempC2, 2);
    Serial.print(",TDS="); Serial.print(tdsValue, 0);
    Serial.print(",pH="); Serial.print(pH, 2);
    Serial.print(",Pitch="); Serial.print(pitch, 2);
    Serial.print(",Roll="); Serial.print(roll, 2);
    Serial.print(",Orient="); Serial.print(orientation);

    Serial.print("|SONAR:");
    Serial.print(dist_front, 1);
    Serial.print(",");
    Serial.print(dist_left, 1);
    Serial.print(",");
    Serial.println(dist_right, 1);
  }

}
