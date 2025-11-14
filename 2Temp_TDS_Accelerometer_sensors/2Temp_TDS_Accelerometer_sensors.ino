#include <OneWire.h>
#include <DallasTemperature.h>

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>

#define TEMP_SENSOR_1 2
#define TEMP_SENSOR_2 3

#define TDS_SENSOR    A0

Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

#define VREF   5.0 
#define SCOUNT 125      // number of samples ≈ 5s at 40 ms/sample (125 * 40ms = 5sec)

int   analogBuffer[SCOUNT];
int   analogBufferTemp[SCOUNT];
int   analogBufferIndex = 0;

float averageVoltage = 0.0;
float tdsValue       = 0.0;

OneWire oneWire1(TEMP_SENSOR_1);
OneWire oneWire2(TEMP_SENSOR_2);

DallasTemperature TempSensor1(&oneWire1);   // temp from D2 - water temp - also for TDS reference
DallasTemperature TempSensor2(&oneWire2);   // temp from D3 - air temperature

// timing
unsigned long analogSampleTimepoint = 0;   // used for 40 ms sampling
unsigned long printTimepoint        = 0;   //used for 5 s printing

//TDS median filtering algorithm
int getMedianNum(int bArray[], int iFilterLen) {
  int bTab[SCOUNT];
  for (byte i = 0; i < iFilterLen; i++) {
    bTab[i] = bArray[i];
  }

  int i, j, bTemp;
  for (j = 0; j < iFilterLen - 1; j++) {
    for (i = 0; i < iFilterLen - j - 1; i++) {
      if (bTab[i] > bTab[i + 1]) {
        bTemp      = bTab[i];
        bTab[i]    = bTab[i + 1];
        bTab[i + 1]= bTemp;
      }
    }
  }

  if ((iFilterLen & 1) > 0) {
    bTemp = bTab[(iFilterLen - 1) / 2];
  } else {
    bTemp = (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
  }
  return bTemp;
}

float readTempC(DallasTemperature &sensor) {
  sensor.requestTemperatures();
  return sensor.getTempCByIndex(0); //always index 0 since one pin per sensor
}

void setup() {
  Serial.begin(115200);
  pinMode(TDS_SENSOR, INPUT);

  TempSensor1.begin();
  TempSensor2.begin();

  Wire.begin();
  if (!accel.begin()) {
    Serial.println("No ADXL345 detected!");
    while (1); // stop here if not found
  }

  accel.setRange(ADXL345_RANGE_2_G);

  //initialize timers
  unsigned long now = millis();
  analogSampleTimepoint = now;
  printTimepoint        = now;
}

void loop() {
  unsigned long now = millis();

  //collect TDS sample every 40ms
  if (now - analogSampleTimepoint >= 40U) {
    analogSampleTimepoint += 40U;    // or analogSampleTimepoint = now;

    analogBuffer[analogBufferIndex] = analogRead(TDS_SENSOR); // store into buffer
    analogBufferIndex++;
    if (analogBufferIndex == SCOUNT) {
      analogBufferIndex = 0;
    }
  }

  //Every 5 seconds: determine senssor readings
  if (now - printTimepoint >= 5000U) {
    printTimepoint += 5000U;        // or printTimepoint = now;

    for (int copyIndex = 0; copyIndex < SCOUNT; copyIndex++) {
      analogBufferTemp[copyIndex] = analogBuffer[copyIndex];
    }

    averageVoltage = getMedianNum(analogBufferTemp, SCOUNT) * (float)VREF / 1024.0;

    // read temps ONLY once every 5 seconds
    float tempC1 = readTempC(TempSensor1); //water temp
    float tempC2 = readTempC(TempSensor2); //air temp

    //temperature compensation using water temp reading as reference
    float compensationCoefficient = 1.0 + 0.02 * (tempC1 - 25.0);
    float compensationVoltage     = averageVoltage / compensationCoefficient;

    //convert the voltage value to tds value
    tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage
               - 255.86 * compensationVoltage * compensationVoltage
               + 857.39 * compensationVoltage) * 0.5;

    //read accelerometer 
    sensors_event_t event;
    accel.getEvent(&event);

    // determine orientation of the accelerometer
    const char* orientation;
    if (event.acceleration.z < -0)      orientation = "Upside Down";
    else if (event.acceleration.z > 6)  orientation = "Upright";
    else                                orientation = "Tilted";

    Serial.print("Temp1 D2: ");
    (tempC1 <= -100.0f) ? Serial.print("ERR") : Serial.print(tempC1, 2);
    Serial.print(" °C || Temp2 D3: ");
    (tempC2 <= -100.0f) ? Serial.print("ERR") : Serial.print(tempC2, 2);
    Serial.print(" °C || TDS: ");
    Serial.print(tdsValue, 0);
    Serial.print(" ppm || Orientation: ");
    Serial.println(orientation); 
  }

  // no delay() needed
}
