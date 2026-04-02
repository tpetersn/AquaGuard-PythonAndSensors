// ==========================================
// 3x JSNR04T-2.0 Sonar Sequential Firing
// Format output for Pi: "SONAR:front,left,right"
// ==========================================

// ⚠️ Salim: Please update these pins to match your actual wiring!
const int TRIG_FRONT = 7;
const int ECHO_FRONT = 6;

const int TRIG_LEFT = 5;
const int ECHO_LEFT = 4;

const int TRIG_RIGHT = 9;
const int ECHO_RIGHT = 8;

void setup() {
  Serial.begin(9600);
  
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

// Helper function to read distance from a single sonar
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

void loop() {
  // 1. Fire FRONT
  float dist_front = readSonar(TRIG_FRONT, ECHO_FRONT);
  delay(60); // Strict 60ms delay to prevent acoustic crosstalk from bouncing waves

  // 2. Fire LEFT
  float dist_left = readSonar(TRIG_LEFT, ECHO_LEFT);
  delay(60); // Strict 60ms delay

  // 3. Fire RIGHT
  float dist_right = readSonar(TRIG_RIGHT, ECHO_RIGHT);
  delay(60); // Strict 60ms delay

  // 4. Pack the three readings into a single line for the Raspberry Pi
  // Format expected by Pi: SONAR:front,left,right
  Serial.print("SONAR:");
  Serial.print(dist_front, 1); // Print with 1 decimal place
  Serial.print(",");
  Serial.print(dist_left, 1);
  Serial.print(",");
  Serial.println(dist_right, 1); // Use println for the last value to add a newline
}