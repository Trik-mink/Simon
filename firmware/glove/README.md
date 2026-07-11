# ProjectedGlove Firmware

Wireless gesture glove for Projected Copilot. A Seeed XIAO ESP32-C3 reads four
flex sensors, classifies a gesture, and sends the gesture name over BLE. The
Python side (`projected_copilot/glove_input.py`) subscribes and feeds the same
queue the keyboard stub uses — so `app.py` is unchanged.

## Parts

- Seeed XIAO ESP32-C3 (BLE + onboard LiPo charging)
- 2× flex sensors (2.2"): index and pinky
- 2× 10kΩ resistors (voltage dividers)
- 150mAh LiPo battery (JST connector)
- Fingerless glove

## Wiring

Each finger is a voltage divider into one ADC pin:

```
3V3 ── flex sensor ──┬── ADC pin
                     └── 10kΩ ── GND
```

| Finger | ADC pin | XIAO GPIO |
|--------|---------|-----------|
| Index  | A0      | GPIO2     |
| Pinky  | A1      | GPIO3     |

Battery: LiPo JST into the XIAO's battery pads (B+ / B-). It charges over USB-C.

## Bring-up order (lowest risk first)

1. **Validate BLE with no sensors** — flash `glove_button_test/`. Wire a button
   from GPIO3 to GND (or use the BOOT button). Each press cycles through the 5
   gesture names. This proves the whole wireless path works before you trust any
   sensor.
2. **Run the app in BLE mode:**
   ```bash
   pip install bleak
   GLOVE_BLE=true python -m projected_copilot.app --windowed
   ```
   Press the button → Simon should react to each gesture. If this works, the
   pipeline is done.
3. **Add sensors** — flash `glove_flex/`. Open Serial Monitor (115200), hold each
   finger straight then bent, read the raw values, and set `BENT_THRESHOLD[]` to
   a midpoint per finger. Flip the `> threshold` comparison in `isBent()` if your
   divider reads the other way.

## Full build walkthrough

Ordered lowest-risk-first, so each step proves the next one can be trusted.

### Phase 0 — Tooling (do once, no hardware)

1. Arduino IDE → Boards Manager → install **"esp32" by Espressif**. Select board
   **XIAO_ESP32C3**.
2. Plug the XIAO in over USB-C and pick its port under Tools → Port.
3. Python side:
   ```bash
   cd ~/ProjectedCopilot
   pip install -r requirements.txt
   pip install bleak          # BLE backend, imported lazily
   ```
4. Make sure `server/.env` has your `ANTHROPIC_API_KEY` (needed for the full app,
   not for the BLE test).

### Phase 1 — Prove the wireless path (no sensors yet)

The most important de-risking step. If BLE works with a button, everything
downstream is just sensor tuning.

5. Upload `glove_button_test/glove_button_test.ino`.
6. Wire a button from **GPIO3 (D1)** to **GND**, or use the onboard **BOOT
   button**. Internal pull-up is used, so no resistor needed.
7. Open Serial Monitor at **115200**. You should see the advertising message.
8. Each press prints `sent: stop`, then `ask`, `speak`, `scan`, `reveal`, looping.

### Phase 2 — Prove the full app reacts

9. With the sketch still running, start the app in BLE mode:
   ```bash
   cd ~/ProjectedCopilot
   GLOVE_BLE=true python -m projected_copilot.app --windowed
   ```
10. Python scans for `ProjectedGlove`, auto-connects, and subscribes. Press the
    button → Simon should react to each gesture. **If this works, the pipeline is
    done** — everything left is making flex sensors emit those same 5 names.

### Phase 3 — Build and calibrate ONE finger

Don't wire all four at once, or you can't tell which divider is wrong.

11. Plug the XIAO across the breadboard's center channel. Build one divider for
    the index finger:
    ```
    3V3 ── flex sensor ──┬── A0 (GPIO2)
                         └── 10kΩ ── GND
    ```
12. Upload `glove_flex/glove_flex.ino`, open Serial Monitor at **115200**. It
    prints raw values once per second.
13. Hold the finger straight, note `idx`. Fully bend it, note `idx` again — two
    distinct numbers in the 0–4095 range.
14. Pick the midpoint between straight and bent — that's your index threshold.

### Phase 4 — Add the pinky, set thresholds

15. Wire pinky → **A1 (GPIO3)** with its own identical divider. Re-check the
    printout so you can read both `idx` and `pnk`.
16. Set your two midpoints in `glove_flex.ino`, order index, pinky:
    ```cpp
    int BENT_THRESHOLD[2] = {2000, 2000};  // ← your real numbers
    ```
17. **Direction check:** the code treats `raw > threshold` as *bent*. If a finger
    reads *lower* when bent, flip that comparison to `<` in `isBent()`. Re-upload.
18. Make each hand shape and confirm the `sent:` line matches the gesture map
    below.

### Phase 5 — Run it live, then move to the glove

19. Re-run the Phase 2 command and drive Simon with real gestures.
20. Once solid on the breadboard, transfer the dividers to the fingerless glove
    (perfboard or direct solder), and connect the 150mAh LiPo to the XIAO's
    B+ / B- pads — it charges over USB-C.

## Gesture map (2-sensor flex firmware)

`true` = finger bent. With only index + pinky, the glove fires three gestures.
**Open palm (both straight) is the neutral resting pose — it sends nothing**, so
it can never be mistaken for a command. Return to open palm between gestures.

| Gesture | index | pinky | Hand shape |
|---------|-------|-------|------------|
| scan    | bent  | bent  | fist — both bent |
| reveal  | bent  | —     | pinky up — index curled, pinky out |
| ask     | —     | bent  | index up — index out, pinky curled |
| _(none)_ | —    | —     | open palm — neutral, sends nothing |

**stop** and **speak** aren't on the glove — use keyboard `1` (stop) and `3`
(speak) in the projector window, or the web panel.

## Must match Python

`DEVICE_NAME`, `SERVICE_UUID`, and `CHAR_UUID` in both `.ino` files must equal
the constants in `projected_copilot/glove_input.py`. If you change one, change
all three.
