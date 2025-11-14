#include <OneWire.h>
#include <DallasTemperature.h>

#define TEMP_SENSOR_1 2
#define TEMP_SENSOR_2 3

#define TDS_SENSOR A0

#define VREF 5.0      //ADC reference voltage
#define SCOUNT 30     //number of samples for TDS median filter

int   analogBuffer[SCOUNT];
int   analogBufferTemp[SCOUNT];
int   analogBufferIndex = 0;

float averageVoltage = 0.0;
float tdsValue       = 0.0;

OneWire oneWire1(TEMP_SENSOR_1);
OneWire oneWire2(TEMP_SENSOR_2);

DallasTemperature TempSensor1(&oneWire1);   //temp from D2 - water temp & for TDS reference
DallasTemperature TempSensor2(&oneWire2);   //temp from D3 - air temp


//TDS median filter algorithm
int getMedianNum(int bArray[], int iFilterLen){
  int bTab[iFilterLen];
  for (byte i = 0; i<iFilterLen; i++)
  bTab[i] = bArray[i];
  int i, j, bTemp;
  for (j = 0; j < iFilterLen - 1; j++) {
    for (i = 0; i < iFilterLen - j - 1; i++) {
      if (bTab[i] > bTab[i + 1]) {
        bTemp = bTab[i];
        bTab[i] = bTab[i + 1];
        bTab[i + 1] = bTemp;
      }
    }
  }
  if ((iFilterLen & 1) > 0){
    bTemp = bTab[(iFilterLen - 1) / 2];
  }
  else {
    bTemp = (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
  }
  return bTemp;
}


void readTempC(DallasTemperature &sensor) {
  sensor.requestTemperatures();
  return sensor.getTempCByIndex(0); //always at index 0 since one pin per sensor
}

void setup() {
  Serial.begin(115200);
  pinMode(TdsSensorPin, INPUT);

  TempSensor1.begin();
  TempSensor2.begin();
}

void loop() {
  float tempC1 = readTempC(TempSensor1);
  float tempC2 = readTempC(tempSensor2);

  //collects TDS sample every 40ms
  static unsigned long analogSampleTimepoint = millis();
  if(millis()-analogSampleTimepoint > 40U){     //every 40 milliseconds,read the analog value from the ADC
    analogSampleTimepoint = millis();
    analogBuffer[analogBufferIndex] = analogRead(TdsSensorPin);    //read the analog value and store into the buffer
    analogBufferIndex++;
    if(analogBufferIndex == SCOUNT){ 
      analogBufferIndex = 0;
    }
  } 

  static unsigned long printTimepoint = millis();
  if(millis()-printTimepoint > 800U){
    printTimepoint = millis();

    for(copyIndex=0; copyIndex<SCOUNT; copyIndex++){
      analogBufferTemp[copyIndex] = analogBuffer[copyIndex];
      
      // read the analog value more stable by the median filtering algorithm, and convert to voltage value
      averageVoltage = getMedianNum(analogBufferTemp,SCOUNT) * (float)VREF / 1024.0;

      float compensationCoefficient = 1.0+0.02*(tempC1 - 25.0); //using tempC1 (water temp as reference temp)
      float compensationVoltage=averageVoltage/compensationCoefficient;
      
      //convert voltage value to tds value
      tdsValue=(133.42 * compensationVoltage * compensationVoltage * compensationVoltage
               - 255.86 * compensationVoltage * compensationVoltage + 857.39 * compensationVoltage) * 0.5;
      

    Serial.print("Temp1 D2: ");
    (tempC1 <= -100.0f) ? Serial.print("ERR") : Serial.print(tempC1, 2);
    Serial.print(" °C || Temp2 D3: ");
    (tempC2 <= -100.0f) ? Serial.print("ERR") : Serial.print(tempC2, 2);
    Serial.print(" °C || TDS: ");
    Serial.print(tdsValue, 0);
    Serial.println(" ppm");
    }
  }

  delay(800);

}
