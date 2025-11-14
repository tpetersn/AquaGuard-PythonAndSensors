#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>

// Create an ADXL345 object on I2C (SDA=A4, SCL=A5 for Arduino Nano)
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

void setup() {
  Serial.begin(115200);
  Serial.println("ADXL345 Orientation Test (SDA=A4, SCL=A5)");

  // Initialize the sensor
  if (!accel.begin()) {
    Serial.println("No ADXL345 detected — check wiring or I2C address!");
    while (1);
  }

  // Set measurement range: ±2G for highest sensitivity
  //accel.setRange(ADXL345_RANGE_2_G);

  Serial.println("ADXL345 connected successfully!");
  Serial.println("--------------------------------");
  Serial.println("X (m/s²)\tY (m/s²)\tZ (m/s²)\tOrientation");
}

void loop() {
  sensors_event_t event;
  accel.getEvent(&event);

  // Print the acceleration values
  Serial.print(event.acceleration.x); Serial.print("\t");
  Serial.print(event.acceleration.y); Serial.print("\t");
  Serial.print(event.acceleration.z); Serial.print("\t");

  // Simple orientation detection
  if (event.acceleration.z < -7) {
    Serial.println("Upside Down");
  } else if (event.acceleration.z > 7) {
    Serial.println("Upright");
  } else {
    Serial.println("Tilted");
  }

  delay(500);
}
