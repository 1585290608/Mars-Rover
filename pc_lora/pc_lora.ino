#include <SPI.h>
#include <LoRa.h>

const long LORA_FREQ = 868E6;
String usbLine;

bool isHexNibble(char c) {
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F');
}

bool looksLikeCompactFrame(const String &text) {
  if (text.length() < 2) {
    return false;
  }

  char a = text.charAt(0);
  char b = text.charAt(1);
  if (!isHexNibble(a) || !isHexNibble(b)) {
    return false;
  }

  return text.length() == 2 || text.charAt(2) == '|';
}

String encodeCommand(const String &payload) {
  String normalized = payload;
  normalized.trim();
  normalized.toUpperCase();

  if (looksLikeCompactFrame(normalized)) {
    return normalized;
  }

  if (normalized == "HELLO") return "0A";
  if (normalized == "STATUS") return "0B";
  if (normalized == "READ_ACCEL") return "0C";
  if (normalized == "LED_ON") return "0D";
  if (normalized == "LED_OFF") return "0E";
  if (normalized == "FORWARD") return "10";
  if (normalized == "BACKWARD") return "11";
  if (normalized == "LEFT") return "12";
  if (normalized == "RIGHT") return "13";
  if (normalized == "STOP") return "14";
  if (normalized == "PING") return "15";
  return normalized;
}

void trace(const String &message) {
  Serial.print("TRACE:");
  Serial.println(message);
}

void setup() {
  Serial.begin(9600);
  while (!Serial) {
  }

  trace("BOOT:PC_LORA_START");

  if (!LoRa.begin(LORA_FREQ)) {
    trace("LORA_INIT_FAILED");
    while (1) {
      delay(1000);
    }
  }

  trace("LORA_INIT_OK");
  trace("READY:TYPE_COMMAND_AND_PRESS_ENTER");
}

void loop() {
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      usbLine.trim();
      if (usbLine.length() > 0) {
        sendLoRa(usbLine);
        usbLine = "";
      }
      continue;
    }
    usbLine += c;
  }

  int packetSize = LoRa.parsePacket();
  if (packetSize > 0) {
    String incoming = LoRa.readString();
    incoming.trim();
    if (incoming.length() > 0) {
      Serial.print("RX: ");
      Serial.println(incoming);
    }
  }
}

void sendLoRa(const String &payload) {
  String wirePayload = encodeCommand(payload);
  if (wirePayload != payload) {
    trace(String("ENCODE:") + payload + "->" + wirePayload);
  }
  trace(String("LOCAL_TX:") + wirePayload);
  LoRa.beginPacket();
  LoRa.print(wirePayload);
  LoRa.endPacket();
}
