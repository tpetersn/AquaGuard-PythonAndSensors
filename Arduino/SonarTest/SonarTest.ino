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
  Serial.println("JSNR04T-2.0 sonar test ready");
  Serial.print("Echo pin state: ");
  Serial.println(digitalRead(ECHO_PIN));
}

void loop() {
  // Send 20us trigger pulse (JSNR04T may need longer than 10us)
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(5);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(20);
  digitalWrite(TRIG_PIN, LOW);

  // Read echo pulse duration (timeout 60ms for JSNR04T's longer range)
  long duration = pulseIn(ECHO_PIN, HIGH, 60000);

  if (duration == 0) {
    Serial.print("No echo (pin=");
    Serial.print(digitalRead(ECHO_PIN));
    Serial.println(") - check wiring: VCC=5V, Trig=D7, Echo=D5");
  } else {
    float distanceCm = duration * 0.0343 / 2.0;
    Serial.print("Distance: ");
    Serial.print(distanceCm, 1);
    Serial.print(" cm  (raw=");
    Serial.print(duration);
    Serial.println(" us)");
  }

  delay(600);  // JSNR04T needs at least 200ms between measurements
}
