/*
 * ProjectedGlove — BLE pipeline validation sketch
 * Board: Seeed XIAO ESP32-C3 (Arduino core for ESP32)
 *
 * PURPOSE: Prove the whole wireless path works BEFORE wiring any flex sensors.
 * Each press of the BOOT button (or a button on D1 to GND) sends the NEXT
 * gesture name in rotation over BLE notify. Run the app with GLOVE_BLE=true and
 * watch Simon react to all five gestures.
 *
 * UUIDs and device name MUST match projected_copilot/glove_input.py.
 *
 * Install once in Arduino IDE:
 *   - Boards Manager → "esp32" by Espressif
 *   - Select board: "XIAO_ESP32C3"
 */

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define DEVICE_NAME  "ProjectedGlove"
#define SERVICE_UUID "a1c00001-5b1e-4b3a-9f00-d3c0ffee0001"
#define CHAR_UUID    "a1c00002-5b1e-4b3a-9f00-d3c0ffee0002"

// Button between this pin and GND, using the internal pull-up.
// D1 on the XIAO ESP32-C3 maps to GPIO3.
const int BUTTON_PIN = 3;

const char* GESTURES[] = {"stop", "ask", "speak", "scan", "reveal"};
const int   NUM_GESTURES = 5;

BLECharacteristic* gestureChar = nullptr;
bool deviceConnected = false;
int  gestureIndex = 0;
int  lastButton = HIGH;
unsigned long lastPressMs = 0;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* s) override { deviceConnected = true; }
  void onDisconnect(BLEServer* s) override {
    deviceConnected = false;
    BLEDevice::startAdvertising();  // allow the laptop to reconnect
  }
};

void sendGesture(const char* name) {
  if (!deviceConnected || gestureChar == nullptr) return;
  gestureChar->setValue((uint8_t*)name, strlen(name));
  gestureChar->notify();
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  BLEDevice::init(DEVICE_NAME);
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  BLEService* service = server->createService(SERVICE_UUID);
  gestureChar = service->createCharacteristic(
      CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  gestureChar->addDescriptor(new BLE2902());
  service->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  // Don't advertise the 128-bit service UUID — name + UUID overflows the 31-byte
  // adv limit and the glove ends up invisible. Python finds it by NAME.
  adv->setScanResponse(true);
  adv->setMinPreferred(0x06);
  adv->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("ProjectedGlove advertising. Press button to cycle gestures.");
}

void loop() {
  int button = digitalRead(BUTTON_PIN);

  // Falling edge with 200ms debounce = one press.
  if (lastButton == HIGH && button == LOW && millis() - lastPressMs > 200) {
    lastPressMs = millis();
    const char* g = GESTURES[gestureIndex];
    sendGesture(g);
    Serial.printf("sent: %s\n", g);
    gestureIndex = (gestureIndex + 1) % NUM_GESTURES;
  }
  lastButton = button;

  delay(10);
}
