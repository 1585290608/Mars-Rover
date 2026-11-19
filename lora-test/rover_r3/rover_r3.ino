#include <SoftwareSerial.h>

String commandLine;
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

void setup() {
  Serial.begin(9600);
  bridgeSerial.begin(BRIDGE_BAUD);

  pinMode(LEFT_IN1, OUTPUT);
  pinMode(LEFT_IN2, OUTPUT);
  pinMode(RIGHT_IN1, OUTPUT);
  pinMode(RIGHT_IN2, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  digitalWrite(LED_PIN, LOW);
  stopMotors();

  debugLog("R3 bridge on SoftwareSerial D2/D3");
  debugLog(String("R3 bridge baud=") + BRIDGE_BAUD);
  emitResponse("A0", "R3_BOOT_OK");
}

void loop() {
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
                     ",IMU=OFF,MOTION=" + currentMotion;
    emitResponse("8B", String("STATUS:") + payload, payload);
    return;
  }

  if (cmd == "READ_ACCEL") {
    emitResponse("9C", "ACCEL_OFFLINE");
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
