#include <OneWire.h>
#include <DallasTemperature.h>

// temp1 is connected to Pin D2 
//temp2 is connected to Pin D3
#define TEMP_SENSOR_1 2
#define TEMP_SENSOR_2 3

// Setup a oneWire instance to communicate with any OneWire devices
OneWire oneWire1(TEMP_SENSOR_1);
OneWire oneWire2(TEMP_SENSOR_2);

// Pass our oneWire reference to Dallas Temperature sensor 
DallasTemperature sensor1(&oneWire1);
DallasTemperature sensor2(&oneWire2);

void setup(void)
{
  Serial.begin(9600);

  sensor1.begin();
  sensor2.begin();
}

void readTempC(DallasTemperature &sensor) {
  sensor.requestTemperatures();
  return sensor.getTempCByIndex(0); //always at index 0 since one pin per sensor
}

void loop(void){ 
  float temp1 = readTempC(sensor1);
  float temp2 = readTempC(sensor2);


  Serial.print("Temp1 (D2): ");
  Serial.print(temp1, 2); 

  Serial.print(" °C || Temp2 (D3): ");
  Serial.print(temp2, 2); 
  Serial.println(" °C");

  delay(1000);
}