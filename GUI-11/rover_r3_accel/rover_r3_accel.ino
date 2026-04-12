#include <Wire.h>
#include <SoftwareSerial.h>
#include <Adafruit_MMA8451.h>
#include <Adafruit_Sensor.h>

Adafruit_MMA8451 mma = Adafruit_MMA8451();

String commandLine;
String usbCommandLine;
String currentMotion = "STOP";

const int LORA_RX_PIN = 2;
const int LORA_TX_PIN = 3;
const unsigned long BRIDGE_BAUD = 4800;
SoftwareSerial bridgeSerial(LORA_RX_PIN, LORA_TX_PIN);

const int LEFT_IN1 = 8;
const int LEFT_IN2 = 9;
const int RIGHT_IN1 = 10;
const int RIGHT_IN2 = 11;
const int LED_PIN = 13;

bool imuReady = false;
const int ACCEL_INIT_RETRIES = 6;
const unsigned long ACCEL_INIT_DELAY_MS = 300;

struct CommandEntry {
  const char *code;
  const char *name;
};

const CommandEntry COMMAND_TABLE[] = {
  {"0A", "HELLO"},
  {"0B", "STATUS"},
  {"0C", "READ_ACCEL"},
  {"0D", "LED_ON"},
  {"0E", "LED_OFF"},
  {"10", "FORWARD"},
  {"11", "BACKWARD"},
  {"12", "LEFT"},
  {"13", "RIGHT"},
  {"14", "STOP"},
  {"15", "PING"}
};

void emitCompactFrame(const String &code, const String &payload = "") {
  String line = code;
  if (payload.length() > 0) {
    line += "|";
    line += payload;
  }
  bridgeSerial.println(line);
  Serial.print("RESP_COMPACT:");
  Serial.println(line);
}

void emitVerboseResponse(const String &text) {
  Serial.print("RESP:");
  Serial.println(text);
}

void emitResponse(const String &code, const String &text, const String &payload = "") {
  emitCompactFrame(code, payload);
  emitVerboseResponse(text);
}

void debugLog(const String &text) {
  Serial.print("DEBUG:");
  Serial.println(text);
}

void debugError(const String &text) {
  Serial.print("ERROR:");
  Serial.println(text);
}

String canonicalCommand(const String &incoming) {
  String cleaned = "";
  for (unsigned int i = 0; i < incoming.length(); ++i) {
    char c = incoming.charAt(i);
    if (c >= 32 && c <= 126) {
      cleaned += c;
    }
  }

  cleaned.trim();
  cleaned.toUpperCase();

  for (unsigned int i = 0; i < sizeof(COMMAND_TABLE) / sizeof(COMMAND_TABLE[0]); ++i) {
    String code = COMMAND_TABLE[i].code;
    String name = COMMAND_TABLE[i].name;
    if (cleaned == code || cleaned == name) {
      return name;
    }
  }

  for (unsigned int i = 0; i < sizeof(COMMAND_TABLE) / sizeof(COMMAND_TABLE[0]); ++i) {
    String code = COMMAND_TABLE[i].code;
    String name = COMMAND_TABLE[i].name;
    if (cleaned.indexOf(name) >= 0 || cleaned.indexOf(code) >= 0) {
      debugLog(String("RECOVERED_CMD:") + name + " FROM:" + cleaned);
      return name;
    }
  }

  return cleaned;
}

void setMotionPins(int leftIn1, int leftIn2, int rightIn1, int rightIn2) {
  digitalWrite(LEFT_IN1, leftIn1);
  digitalWrite(LEFT_IN2, leftIn2);
  digitalWrite(RIGHT_IN1, rightIn1);
  digitalWrite(RIGHT_IN2, rightIn2);
}

void stopMotors() {
  setMotionPins(LOW, LOW, LOW, LOW);
  currentMotion = "STOP";
}

void driveForward() {
  setMotionPins(HIGH, LOW, HIGH, LOW);
  currentMotion = "FORWARD";
}

void driveBackward() {
  setMotionPins(LOW, HIGH, LOW, HIGH);
  currentMotion = "BACKWARD";
}

void rotateLeft() {
  setMotionPins(LOW, HIGH, HIGH, LOW);
  currentMotion = "LEFT";
}

void rotateRight() {
  setMotionPins(HIGH, LOW, LOW, HIGH);
  currentMotion = "RIGHT";
}

bool probeAccel(bool announceResult) {
  debugLog("MMA8451 probe start");
  if (mma.begin()) {
    imuReady = true;
    mma.setRange(MMA8451_RANGE_2_G);
    debugLog("MMA8451 initialized");
    debugLog("MMA8451 range=2G");
    if (announceResult) {
      emitResponse("9E", "ACCEL_OK");
    }
    return true;
  }

  imuReady = false;
  debugError("MMA8451 not found on I2C");
  if (announceResult) {
    emitResponse("9D", "MMA8451_OFFLINE");
  }
  return false;
}

bool ensureAccelReady(bool announceResult) {
  if (imuReady) {
    return true;
  }

  for (int attempt = 0; attempt < ACCEL_INIT_RETRIES; ++attempt) {
    debugLog(String("MMA8451 probe attempt=") + (attempt + 1));
    if (probeAccel(false)) {
      if (announceResult) {
        emitResponse("9E", "ACCEL_OK");
      }
      return true;
    }
    delay(ACCEL_INIT_DELAY_MS);
  }

  if (announceResult) {
    emitResponse("9D", "MMA8451_OFFLINE");
  }
  return false;
}

bool readAccelPayload(String &payload) {
  if (!ensureAccelReady(false)) {
    return false;
  }

  sensors_event_t event;
  mma.getEvent(&event);

  float ax = event.acceleration.x;
  float ay = event.acceleration.y;
  float az = event.acceleration.z;

  payload = String(ax, 3) + "," + String(ay, 3) + "," + String(az, 3);
  debugLog(String("ACCEL_MPS2:") + payload);
  return true;
}

void setup() {
  Serial.begin(9600);
  bridgeSerial.begin(BRIDGE_BAUD);
  Wire.begin();

  pinMode(LEFT_IN1, OUTPUT);
  pinMode(LEFT_IN2, OUTPUT);
  pinMode(RIGHT_IN1, OUTPUT);
  pinMode(RIGHT_IN2, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  digitalWrite(LED_PIN, LOW);
  stopMotors();
  debugLog("R3 accel bridge on SoftwareSerial D2/D3");
  debugLog(String("R3 bridge baud=") + BRIDGE_BAUD);
  debugLog("USB local commands enabled");
  debugLog("Try local commands: READ_ACCEL, STATUS, HELLO");

  if (!ensureAccelReady(true)) {
    debugError("MMA8451 remained offline after retries");
  }

  emitResponse("A0", "R3_BOOT_OK");
}

void loop() {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      usbCommandLine.trim();
      if (usbCommandLine.length() > 0) {
        debugLog(String("USB_CMD=") + usbCommandLine);
        handleCommand(usbCommandLine);
        usbCommandLine = "";
      }
      continue;
    }
    usbCommandLine += c;
  }

  while (bridgeSerial.available()) {
    char c = static_cast<char>(bridgeSerial.read());
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      commandLine.trim();
      if (commandLine.length() > 0) {
        handleCommand(commandLine);
        commandLine = "";
      }
      continue;
    }
    commandLine += c;
  }
}

void handleCommand(String incoming) {
  incoming.trim();
  debugLog(String("CMD=") + incoming);
  String cmd = canonicalCommand(incoming);
  if (cmd != incoming) {
    debugLog(String("CMD_CANONICAL=") + cmd);
  }

  if (cmd == "HELLO" || cmd == "PING") {
    emitResponse("8A", "HELLO_OK");
    return;
  }

  if (cmd == "STATUS") {
    String payload = String("LED=") +
                     (digitalRead(LED_PIN) == HIGH ? "ON" : "OFF") +
                     ",IMU=" + (imuReady ? "ON" : "OFF") +
                     ",MOTION=" + currentMotion;
    emitResponse("8B", String("STATUS:") + payload, payload);
    return;
  }

  if (cmd == "READ_ACCEL") {
    String payload = "";
    if (!readAccelPayload(payload)) {
      emitResponse("9C", "ACCEL_OFFLINE");
      return;
    }

    emitResponse("8C", String("ACCEL:") + payload, payload);
    return;
  }

  if (cmd == "LED_ON") {
    digitalWrite(LED_PIN, HIGH);
    emitResponse("8D", "LED=ON");
    return;
  }

  if (cmd == "LED_OFF") {
    digitalWrite(LED_PIN, LOW);
    emitResponse("8E", "LED=OFF");
    return;
  }

  if (cmd == "FORWARD") {
    driveForward();
    emitResponse("90", "FORWARD");
    return;
  }

  if (cmd == "BACKWARD") {
    driveBackward();
    emitResponse("91", "BACKWARD");
    return;
  }

  if (cmd == "LEFT") {
    rotateLeft();
    emitResponse("92", "LEFT");
    return;
  }

  if (cmd == "RIGHT") {
    rotateRight();
    emitResponse("93", "RIGHT");
    return;
  }

  if (cmd == "STOP") {
    stopMotors();
    emitResponse("94", "STOP");
    return;
  }

  emitResponse("9F", String("ERROR:UNKNOWN=") + incoming, String("UNKNOWN=") + incoming);
}
