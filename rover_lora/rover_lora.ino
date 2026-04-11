#include <MKRWAN.h>

LoRaModem modem;

const unsigned long USB_BAUD = 9600;
const unsigned long R3_UART_BAUD = 4800;
const unsigned long R3_RESPONSE_TIMEOUT_MS = 5000;
const int MODEM_DATA_RATE = 5;
const int MODEM_PORT = 1;
const int MODEM_CHANNEL = 0;

String r3Line;
String usbLine;
String pendingCommand;
unsigned long lastCommandMillis = 0;
bool waitingForR3 = false;

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

bool isAllowedRequestCode(const String &code) {
  return code == "0A" || code == "0B" || code == "0C" || code == "0D" ||
         code == "0E" || code == "10" || code == "11" || code == "12" ||
         code == "13" || code == "14" || code == "15";
}

bool isAllowedTextCommand(const String &text) {
  return text == "HELLO" || text == "STATUS" || text == "READ_ACCEL" ||
         text == "LED_ON" || text == "LED_OFF" || text == "FORWARD" ||
         text == "BACKWARD" || text == "LEFT" || text == "RIGHT" ||
         text == "STOP" || text == "PING";
}

String normalizeCommand(const String &incoming) {
  String normalized = incoming;
  normalized.trim();
  normalized.toUpperCase();
  return normalized;
}

bool isAllowedInboundCommand(const String &incoming) {
  String normalized = normalizeCommand(incoming);
  if (normalized.length() == 0) {
    return false;
  }

  if (looksLikeCompactFrame(normalized)) {
    return isAllowedRequestCode(normalized.substring(0, 2));
  }

  return isAllowedTextCommand(normalized);
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

  Serial1.begin(R3_UART_BAUD);
  delay(2000);
  trace("BOOT:ROVER_LORA_START");

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
  trace("USB_MONITOR_ONLY");
  trace(String("R3_UART_BAUD:") + R3_UART_BAUD);
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
        trace(String("USB_IGNORED:") + usbLine);
        usbLine = "";
      }
      continue;
    }
    usbLine += c;
  }

  int packetSize = modem.parsePacket();
  if (packetSize > 0) {
    String incoming = modem.readString();
    incoming = normalizeCommand(incoming);
    if (incoming.length() > 0) {
      trace(String("LORA_RX:") + incoming);
      if (isAllowedInboundCommand(incoming)) {
        trace(String("UART_TX:") + incoming);
        Serial1.println(incoming);
        pendingCommand = incoming;
        lastCommandMillis = millis();
        waitingForR3 = true;
      } else {
        trace(String("DROP_INVALID_LORA_PAYLOAD:") + incoming);
      }
    }
  }

  while (Serial1.available()) {
    char c = static_cast<char>(Serial1.read());
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      r3Line.trim();
      if (r3Line.length() > 0) {
        trace(String("R3_RX:") + r3Line);
        if (r3Line.startsWith("RESP:") || r3Line.startsWith("DATA:") || looksLikeCompactFrame(r3Line)) {
          sendLoRa(r3Line);
          waitingForR3 = false;
          pendingCommand = "";
        } else {
          trace(String("DROP_INVALID_R3_PAYLOAD:") + r3Line);
        }
        r3Line = "";
      }
      continue;
    }
    r3Line += c;
  }

  if (waitingForR3 && millis() - lastCommandMillis > R3_RESPONSE_TIMEOUT_MS) {
    trace(String("R3_TIMEOUT:") + pendingCommand);
    waitingForR3 = false;
    pendingCommand = "";
  }
}

void sendLoRa(const String &payload) {
  trace(String("LORA_TX:") + payload);
  modem.beginPacket();
  modem.print(payload);
  int result = modem.endPacket(false);
  if (result <= 0) {
    trace(String("LORA_TX_FAIL:") + payload);
  }
}
