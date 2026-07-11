/*
 * ProjectedGlove — flex-sensor gesture firmware
 * Board: Seeed XIAO ESP32-C3 (Arduino core for ESP32)
 *
 * Reads 2 flex sensors (index + pinky), classifies one of THREE gestures, and
 * sends the gesture name over BLE notify — debounced so each held gesture fires
 * once. UUIDs/name MUST match projected_copilot/glove_input.py.
 *
 * Open palm (both straight) is the NEUTRAL resting pose — it sends nothing, so
 * it can't be mistaken for a gesture. The three hand shapes that fire:
 *   index bent,     pinky bent       -> scan    (fist)
 *   index bent,     pinky straight   -> reveal  (pinky up)
 *   index straight, pinky bent       -> ask     (index up)
 * "stop" and "speak" aren't on the glove — use keyboard '1'/'3' or the web panel.
 *
 * WIRING (per finger, a voltage divider):
 *   3V3 ── flex sensor ──┬── ADC pin (A0 / A1)
 *                        └── 10kΩ ── GND
 *   A straight finger and a bent finger give two different ADC readings.
 *
 * XIAO ESP32-C3 analog pins: A0=GPIO2, A1=GPIO3.
 *
 * CALIBRATION: open the Serial Monitor at 115200. Hold each finger straight,
 * then fully bent, and read the raw values printed each second. Pick a midpoint
 * for each finger and put it in BENT_THRESHOLD below. Higher raw = more bent or
 * less bent depending on which way you wired the divider — the code treats
 * "raw > threshold" as bent; flip the comparison if yours is reversed.
 */

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define DEVICE_NAME  "ProjectedGlove"
#define SERVICE_UUID "a1c00001-5b1e-4b3a-9f00-d3c0ffee0001"
#define CHAR_UUID    "a1c00002-5b1e-4b3a-9f00-d3c0ffee0002"

// Finger -> analog pin (2-sensor build: index + pinky only)
const int PIN_INDEX = A0;
const int PIN_PINKY = A1;

// Per-finger "bent" thresholds — SET THESE from the calibration printout.
// Order: index, pinky. Both sensors read LOWER when bent (see isBent below).
// Index: straight ~1200, bent ~610.  Pinky: straight ~980, bent ~550.
int BENT_THRESHOLD[2] = {900, 765};

// A gesture must hold this long before it fires, then can't refire until
// released — mirrors the old camera detector's hold + cooldown feel.
const unsigned long HOLD_MS = 120;

BLECharacteristic* gestureChar = nullptr;
bool deviceConnected = false;

String candidate = "";
String lastSent = "";
unsigned long candidateSince = 0;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* s) override { deviceConnected = true; }
  void onDisconnect(BLEServer* s) override {
    deviceConnected = false;
    BLEDevice::startAdvertising();
  }
};

void sendGesture(const String& name) {
  if (!deviceConnected || gestureChar == nullptr) return;
  gestureChar->setValue((uint8_t*)name.c_str(), name.length());
  gestureChar->notify();
}

// Returns true if the finger is bent (averaged over a few reads to cut noise).
// This build's dividers read LOWER when bent, so the comparison is "< threshold".
bool isBent(int pin, int threshold) {
  long sum = 0;
  for (int i = 0; i < 4; i++) sum += analogRead(pin);
  return (sum / 4) < threshold;
}

// Map the 2 finger states to a gesture name, or "" for the neutral open palm.
// Returning "" for both-straight gives a real resting pose: relax to open palm
// between gestures, and it can't be mistaken for a command.
String classify(bool idx, bool pnk) {
  if ( idx &&  pnk) return "scan";    // fist — both bent
  if ( idx && !pnk) return "reveal";  // pinky up — index bent, pinky straight
  if (!idx &&  pnk) return "ask";     // index up — index straight, pinky bent
  return "";                          // open palm — both straight — neutral
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);  // 0..4095

  BLEDevice::init(DEVICE_NAME);
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  BLEService* service = server->createService(SERVICE_UUID);
  gestureChar = service->createCharacteristic(
      CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  gestureChar->addDescriptor(new BLE2902());
  service->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  // Do NOT add the 128-bit service UUID to the advertising packet: name (~16B)
  // + 128-bit UUID (~18B) overflows the 31-byte BLE adv limit, so the ESP32
  // silently advertises nothing usable. The Python side finds the glove by
  // NAME, and the service is still reachable after connecting. Keep name only.
  adv->setScanResponse(true);
  adv->setMinPreferred(0x06);
  adv->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("ProjectedGlove (flex) advertising.");
}

unsigned long lastPrint = 0;

void loop() {
  bool idx = isBent(PIN_INDEX, BENT_THRESHOLD[0]);
  bool pnk = isBent(PIN_PINKY, BENT_THRESHOLD[1]);

  // Calibration aid: raw values once per second.
  if (millis() - lastPrint > 1000) {
    lastPrint = millis();
    Serial.printf("raw  idx=%d pnk=%d\n",
                  analogRead(PIN_INDEX), analogRead(PIN_PINKY));
  }

  String g = classify(idx, pnk);

  if (g == "") {
    candidate = "";              // open palm: neutral, allow the next gesture
    lastSent = "";
  } else if (g != candidate) {
    candidate = g;               // a new steady gesture started
    candidateSince = millis();
  } else if (g != lastSent && millis() - candidateSince >= HOLD_MS) {
    sendGesture(g);              // held long enough, not yet sent
    lastSent = g;
    Serial.printf("sent: %s\n", g.c_str());
  }

  delay(15);
}
