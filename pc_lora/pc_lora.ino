#include <SPI.h>
#include <LoRa.h>

const unsigned long USB_BAUD = 9600;
// Change this on both MKR WAN 1310 boards to match your legal regional band.
const long LORA_FREQUENCY_HZ = 868E6;
const byte LORA_SYNC_WORD = 0x34;
const byte LOCAL_ADDRESS = 0xBB;
const byte REMOTE_ADDRESS = 0xCC;

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

String hexByte(byte value) {
  const char *digits = "0123456789ABCDEF";
  String out = "";
  out += digits[(value >> 4) & 0x0F];
  out += digits[value & 0x0F];
  return out;
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

bool configureRadio() {
  if (!LoRa.begin(LORA_FREQUENCY_HZ)) {
    return false;
  }

  LoRa.setSyncWord(LORA_SYNC_WORD);
  return true;
}

void setup() {
  Serial.begin(USB_BAUD);
  unsigned long waitStarted = millis();
  while (!Serial && millis() - waitStarted < 2500) {
  }

  delay(2000);
  trace("BOOT:PC_LORA_START");

  if (!configureRadio()) {
    trace("LORA_INIT_FAILED");
    while (1) {
      delay(1000);
    }
  }

  trace("LORA_INIT_OK");
  trace("LIB:ARDUINO_LORA");
  trace("MURATA_FW_REQ:1.1.6_PLUS");
  trace(String("LORA_FREQUENCY_HZ:") + LORA_FREQUENCY_HZ);
  trace(String("LORA_SYNC_WORD:0x") + hexByte(LORA_SYNC_WORD));
  trace(String("LOCAL_ADDRESS:0x") + hexByte(LOCAL_ADDRESS));
  trace(String("REMOTE_ADDRESS:0x") + hexByte(REMOTE_ADDRESS));
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
    if (packetSize < 2) {
      while (LoRa.available()) {
        LoRa.read();
      }
      trace(String("DROP_SHORT_LORA_PACKET:") + packetSize);
      return;
    }

    byte recipient = static_cast<byte>(LoRa.read());
    byte sender = static_cast<byte>(LoRa.read());
    String incoming = "";
    while (LoRa.available()) {
      incoming += static_cast<char>(LoRa.read());
    }
    incoming.trim();
    incoming.toUpperCase();
    if (incoming.length() > 0) {
      trace(
          String("LORA_RX_META:TO=0x") + hexByte(recipient) +
          ",FROM=0x" + hexByte(sender) +
          ",RSSI=" + LoRa.packetRssi());
      if (recipient != LOCAL_ADDRESS) {
        trace(String("DROP_OTHER_RECIPIENT:0x") + hexByte(recipient));
        return;
      }
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

  trace(
      String("LOCAL_TX:TO=0x") + hexByte(REMOTE_ADDRESS) +
      ",FROM=0x" + hexByte(LOCAL_ADDRESS) +
      ",PAYLOAD=" + wirePayload);
  if (!LoRa.beginPacket()) {
    trace(String("TX_BUSY:") + wirePayload);
    return;
  }
  LoRa.write(REMOTE_ADDRESS);
  LoRa.write(LOCAL_ADDRESS);
  LoRa.print(wirePayload);
  int result = LoRa.endPacket();
  if (!result) {
    trace(String("TX_FAIL:") + wirePayload);
  }
}
