#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

// KY-038
const int micAO = A0;
const int micDO = 8;

// PIR
const int pirPin = 6;

// LEDs
const int soundLed = 7;
const int pirLed = 9;
const int ultraLed = 12;

// Ultrasonic
const int trigPin = 10;
const int echoPin = 11;

// HX711 Load Cell
const int HX_DT = 5;
const int HX_SCK = 4;

int soundThreshold = 15;      // lowered from 20
int distanceThreshold = 50;   // cm

long loadOffset = 0;
long loadThreshold = 5000;

unsigned long lastPrintTime = 0;
unsigned long lastLCDTime = 0;

unsigned long lastSoundTime = 0;
unsigned long lastMotionTime = 0;
unsigned long lastNearTime = 0;
unsigned long lastLoadTime = 0;

const unsigned long holdTime = 2000; // show detection for 2 sec

void setup() {
  Serial.begin(115200);

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("EchoSync Start");
  lcd.setCursor(0, 1);
  lcd.print("Warming up...");

  pinMode(micAO, INPUT);
  pinMode(micDO, INPUT);
  pinMode(pirPin, INPUT);

  pinMode(soundLed, OUTPUT);
  pinMode(pirLed, OUTPUT);
  pinMode(ultraLed, OUTPUT);

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  pinMode(HX_DT, INPUT);
  pinMode(HX_SCK, OUTPUT);

  digitalWrite(soundLed, LOW);
  digitalWrite(pirLed, LOW);
  digitalWrite(ultraLed, LOW);
  digitalWrite(trigPin, LOW);
  digitalWrite(HX_SCK, LOW);

  Serial.println("EchoSync Arduino sensor node starting...");
  Serial.println("Keep load cell empty for tare...");
  delay(3000);

  long tareValue = 0;
  if (readHX711Average(3, tareValue)) {
    loadOffset = tareValue;
    Serial.print("Load cell tare offset: ");
    Serial.println(loadOffset);
  } else {
    Serial.println("HX711 not ready. Continuing without load cell.");
    loadOffset = 0;
  }

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("PIR warm up");
  lcd.setCursor(0, 1);
  lcd.print("Wait 30 sec");

  Serial.println("Wait 30 seconds for PIR warm up...");
  delay(30000);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("EchoSync Ready");
  lcd.setCursor(0, 1);
  lcd.print("Monitoring...");
  Serial.println("Ready!");
}

int readSoundLevel() {
  int minValue = 1023;
  int maxValue = 0;

  for (int i = 0; i < 200; i++) {
    int value = analogRead(micAO);

    if (value < minValue) minValue = value;
    if (value > maxValue) maxValue = value;

    delayMicroseconds(200);
  }

  return maxValue - minValue;
}

float readDistanceCM() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);

  if (duration == 0) {
    return -1;
  }

  return duration * 0.0343 / 2;
}

bool readHX711Raw(long &value) {
  unsigned long startTime = millis();

  while (digitalRead(HX_DT) == HIGH) {
    if (millis() - startTime > 100) {   // shorter timeout so it won't freeze
      return false;
    }
  }

  long count = 0;

  for (int i = 0; i < 24; i++) {
    digitalWrite(HX_SCK, HIGH);
    delayMicroseconds(1);

    count = count << 1;

    digitalWrite(HX_SCK, LOW);
    delayMicroseconds(1);

    if (digitalRead(HX_DT)) {
      count++;
    }
  }

  digitalWrite(HX_SCK, HIGH);
  delayMicroseconds(1);
  digitalWrite(HX_SCK, LOW);
  delayMicroseconds(1);

  if (count & 0x800000) {
    count |= 0xFF000000;
  }

  value = count;
  return true;
}

bool readHX711Average(int times, long &average) {
  long total = 0;
  int successCount = 0;

  for (int i = 0; i < times; i++) {
    long raw = 0;

    if (readHX711Raw(raw)) {
      total += raw;
      successCount++;
    }

    delay(5);
  }

  if (successCount == 0) {
    return false;
  }

  average = total / successCount;
  return true;
}

void updateLCD(bool soundShown, bool motionShown, bool nearShown, bool loadShown, bool possibleFall, float distanceCM) {
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("S:");
  lcd.print(soundShown ? "Y" : "N");

  lcd.print(" P:");
  lcd.print(motionShown ? "Y" : "N");

  lcd.print(" U:");
  lcd.print(nearShown ? "Y" : "N");

  lcd.print(" L:");
  lcd.print(loadShown ? "Y" : "N");

  lcd.setCursor(0, 1);

  if (possibleFall) {
    lcd.print("RISK: FALL");
  } else if (soundShown || motionShown || nearShown || loadShown) {
    lcd.print("ALERT ");

    if (distanceCM == -1) {
      lcd.print("D:--");
    } else {
      lcd.print("D:");
      lcd.print((int)distanceCM);
      lcd.print("cm");
    }
  } else {
    lcd.print("Status: Normal");
  }
}

void loop() {
  int soundLevel = readSoundLevel();
  int micDigital = digitalRead(micDO);
  int pirValue = digitalRead(pirPin);
  float distanceCM = readDistanceCM();

  long loadRaw = 0;
  bool loadReady = readHX711Average(1, loadRaw);
  long loadNet = loadRaw - loadOffset;

  bool soundDetected = soundLevel > soundThreshold;
  bool motionDetected = pirValue == HIGH;
  bool nearDetected = distanceCM > 0 && distanceCM < distanceThreshold;
  bool loadDetected = loadReady && labs(loadNet) > loadThreshold;

  if (soundDetected) lastSoundTime = millis();
  if (motionDetected) lastMotionTime = millis();
  if (nearDetected) lastNearTime = millis();
  if (loadDetected) lastLoadTime = millis();

  bool soundShown = millis() - lastSoundTime < holdTime;
  bool motionShown = millis() - lastMotionTime < holdTime;
  bool nearShown = millis() - lastNearTime < holdTime;
  bool loadShown = millis() - lastLoadTime < holdTime;

  bool possibleFall = soundShown && nearShown && !motionShown;
  bool alert = soundShown || motionShown || nearShown || loadShown;

  digitalWrite(soundLed, soundShown ? HIGH : LOW);
  digitalWrite(pirLed, motionShown ? HIGH : LOW);
  digitalWrite(ultraLed, nearShown ? HIGH : LOW);

  // Update LCD every 500ms
  if (millis() - lastLCDTime >= 500) {
    lastLCDTime = millis();
    updateLCD(soundShown, motionShown, nearShown, loadShown, possibleFall, distanceCM);
  }

  // Print JSON every 1 second for Raspberry Pi
  if (millis() - lastPrintTime >= 1000) {
    lastPrintTime = millis();

    Serial.print("{\"soundLevel\":");
    Serial.print(soundLevel);

    Serial.print(",\"micDigital\":");
    Serial.print(micDigital);

    Serial.print(",\"pirMotion\":");
    Serial.print(pirValue);

    Serial.print(",\"distanceCm\":");
    if (distanceCM == -1) {
      Serial.print(-1);
    } else {
      Serial.print(distanceCM);
    }

    Serial.print(",\"soundDetected\":");
    Serial.print(soundShown ? 1 : 0);

    Serial.print(",\"nearDetected\":");
    Serial.print(nearShown ? 1 : 0);

    Serial.print(",\"loadReady\":");
    Serial.print(loadReady ? 1 : 0);

    Serial.print(",\"loadRaw\":");
    Serial.print(loadRaw);

    Serial.print(",\"loadNet\":");
    Serial.print(loadNet);

    Serial.print(",\"loadDetected\":");
    Serial.print(loadShown ? 1 : 0);

    Serial.print(",\"possibleFall\":");
    Serial.print(possibleFall ? 1 : 0);

    Serial.print(",\"alert\":");
    Serial.print(alert ? 1 : 0);

    Serial.println("}");
  }

  delay(50);
}