#include <SPI.h>
#include <LoRa.h>

const long LORA_FREQ = 868E6;
const unsigned long R3_RESPONSE_TIMEOUT_MS = 5000;
const unsigned long R3_UART_BAUD = 4800;

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

void trace(const String &message) {
  Serial.print("TRACE:");
  Serial.println(message);
}

void setup() {
  Serial.begin(9600);
  Serial1.begin(R3_UART_BAUD);

  trace("BOOT:ROVER_LORA_START");

  if (!LoRa.begin(LORA_FREQ)) {
    trace("LORA_INIT_FAILED");
    while (1) {
      delay(1000);
    }
  }

  trace("LORA_INIT_OK");
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

  int packetSize = LoRa.parsePacket();
  if (packetSize > 0) {
    String incoming = LoRa.readString();
    incoming.trim();
    if (incoming.length() > 0) {
      trace(String("LORA_RX:") + incoming);
      trace(String("UART_TX:") + incoming);
      Serial1.println(incoming);
      pendingCommand = incoming;
      lastCommandMillis = millis();
      waitingForR3 = true;
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
  LoRa.beginPacket();
  LoRa.print(payload);
  LoRa.endPacket();
}
