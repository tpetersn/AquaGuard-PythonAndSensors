// JSNR04T-2.0 Ultrasonic Sonar Sensor Test
// Trig = D7, Echo = D6

const int TRIG_PIN = 7;
const int ECHO_PIN = 6;

void setup() {
  Serial.begin(9600);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  delay(1000);  // JSNR04T needs ~500ms power-on stabilization
}

void loop() {
  // Send 20us trigger pulse
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(5);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(20);
  digitalWrite(TRIG_PIN, LOW);

  // Timeout 60ms covers full range of JSNR04T (~10m)
  long duration = pulseIn(ECHO_PIN, HIGH, 60000);

  if (duration > 0) {
    float distanceCm = duration * 0.0343 / 2.0;
    Serial.print("SONAR:");
    Serial.println(distanceCm, 1);
  }
  // No echo: print nothing — sim keeps last known value

  delay(60);  // ~15 readings/s, well above sim's 25fps
}
