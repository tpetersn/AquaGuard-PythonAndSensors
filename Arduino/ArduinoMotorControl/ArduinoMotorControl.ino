// === BTS7960 Motor Driver + Servo Rudder Control ===

#include <Servo.h>

const int RPWM = 5;   // PWM forward
const int LPWM = 6;   // PWM reverse
const int R_EN = 7;
const int L_EN = 8;

const int SERVO_PIN = 9;

int maxPWM = 180;         // Default speed (0–255)
float deadzone = 0.01;    // Ignore tiny throttle noise
float rudderDeadzone = 0.02; // Ignore tiny rudder noise

Servo rudder;

void setup() {
  Serial.begin(9600);

  pinMode(RPWM, OUTPUT);
  pinMode(LPWM, OUTPUT);
  pinMode(R_EN, OUTPUT);
  pinMode(L_EN, OUTPUT);

  digitalWrite(R_EN, HIGH);
  digitalWrite(L_EN, HIGH);

  stopMotor();
  Serial.println("Arduino ready (motor + rudder mode)");

  // Attach servo
  rudder.attach(SERVO_PIN);
  rudder.write(90);  // center

  // -------------------------------
  // 🚀 AUTO-TEST: Forward speed test
  // -------------------------------
  Serial.println("Starting motor auto-test...");

  int testSpeeds[3] = {85, 170, 255};  // ~33%, ~66%, 100%

  for (int i = 0; i < 3; i++) {
    int pwm = testSpeeds[i];

    Serial.print("Testing speed PWM = ");
    Serial.println(pwm);

    analogWrite(LPWM, 0);   // forward direction
    analogWrite(RPWM, pwm);

    delay(1500); // run each speed for 1.5 seconds

    stopMotor();
    delay(700);  // short pause between steps
  }

  Serial.println("Motor auto-test complete.");
}

void stopMotor() {
  analogWrite(RPWM, 0);
  analogWrite(LPWM, 0);
}

/*
Joystick:
X = throttle (forward/reverse)
Y = steering (rudder)
*/
void driveSingleMotor(float x, float y) {
  // ---------------------
  // Throttle control (X)
  // ---------------------
  if (abs(x) < deadzone) x = 0;

  int pwmValue = abs(x) * maxPWM;

  if (x > 0) {
    analogWrite(LPWM, 0);
    analogWrite(RPWM, pwmValue);
  }
  else if (x < 0) {
    analogWrite(RPWM, 0);
    analogWrite(LPWM, pwmValue);
  }
  else {
    stopMotor();
  }

  // ---------------------
  // Rudder control (Y)
  // ---------------------
  if (abs(y) < rudderDeadzone) y = 0;

  // Map y ∈ [-1, 1] → servo angle ∈ [45°, 135°]
  // 45° = full left, 90° = center, 135° = full right
  int angle = map(y * 100, -100, 100, 45, 135);

  // Constrain to servo-safe range
  angle = constrain(angle, 45, 135);

  rudder.write(angle);

  Serial.print("Rudder angle = ");
  Serial.println(angle);
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line.startsWith("DIR")) {
      line.remove(0, 3);      // remove "DIR"
      line.trim();            // now "1.000 0.000"

      int spaceIndex = line.indexOf(' ');
      if (spaceIndex > 0) {
          String xs = line.substring(0, spaceIndex);
          String ys = line.substring(spaceIndex + 1);

          float x = xs.toFloat();   // throttle
          float y = ys.toFloat();   // rudder

          Serial.print("Parsed throttle x = ");
          Serial.println(x);

          Serial.print("Parsed rudder y   = ");
          Serial.println(y);

          driveSingleMotor(x, y);
      }
    }

    else if (line.startsWith("SPEED")) {
      int val;
      sscanf(line.c_str(), "SPEED %d", &val);
      maxPWM = map(val, 0, 100, 0, 255);
      Serial.print("Max speed set to: ");
      Serial.println(maxPWM);
    }
  }
}
