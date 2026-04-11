#include <MKRWAN.h>

LoRaModem modem;

const unsigned long USB_BAUD = 9600;
const int MODEM_DATA_RATE = 5;
const int MODEM_PORT = 1;
const int MODEM_CHANNEL = 0;

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

bool configureModem() {
  if (!modem.begin(EU868)) {
    return false;
  }

  modem.dataRate(MODEM_DATA_RATE);
  modem.setPort(MODEM_PORT);
  modem.setChannel(MODEM_CHANNEL);
  return true;
}

void setup() {
  Serial.begin(USB_BAUD);
  unsigned long waitStarted = millis();
  while (!Serial && millis() - waitStarted < 2500) {
  }

  delay(2000);
  trace("BOOT:PC_LORA_START");

  if (!configureModem()) {
    trace("LORA_INIT_FAILED");
    while (1) {
      delay(1000);
    }
  }

  trace("LORA_INIT_OK");
  trace(String("MODEM_DR:") + MODEM_DATA_RATE);
  trace(String("MODEM_PORT:") + MODEM_PORT);
  trace(String("MODEM_CHANNEL:") + MODEM_CHANNEL);
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

  int packetSize = modem.parsePacket();
  if (packetSize > 0) {
    String incoming = modem.readString();
    incoming.trim();
    incoming.toUpperCase();
    if (incoming.length() > 0) {
      if (incoming.startsWith("RESP:") || incoming.startsWith("DATA:") || looksLikeCompactFrame(incoming)) {
        Serial.print("RX: ");
        Serial.println(incoming);
      } else {
        trace(String("IGNORED_LORA_PAYLOAD:") + incoming);
      }
    }
  }
}

void sendLoRa(const String &payload) {
  String wirePayload = encodeCommand(payload);
  if (wirePayload.length() == 0) {
    return;
  }

  if (wirePayload != payload) {
    trace(String("ENCODE:") + payload + "->" + wirePayload);
  }

  trace(String("LOCAL_TX:") + wirePayload);
  modem.beginPacket();
  modem.print(wirePayload);
  int result = modem.endPacket(false);
  if (result <= 0) {
    trace(String("TX_FAIL:") + wirePayload);
  }
}
