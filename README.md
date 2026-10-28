# TriSense

**Control your PC with your hand, your voice or your face, with an Arduino control panel that shows what is happening.**

TriSense is a mini-project for Arduino + Python. A laptop webcam and microphone are used for the heavy work
(hand tracking, face tracking, speech recognition). An Arduino Uno acts as a physical control panel:
a button to change mode, LEDs that show the mode and errors, and an LCD that shows the last command.

```
 webcam ──► gesture engine ─┐
 webcam ──► face engine ────┼──► main.py ──► PC actions (volume, click, lock, open sites ...)
 mic    ──► voice engine ───┘       │
                                    └── serial (USB) ◄──► Arduino: button, 4 LEDs, LCD
```

---

## 1. Modes

Only **one mode is active at a time**. Press the Arduino button (or `M` in the camera window) to cycle
**GESTURE → VOICE → FACE → GESTURE ...** Commands from the other modes are ignored.

| Mode | LED | Input |
|---|---|---|
| GESTURE | blue (D8) | hand in front of the webcam |
| VOICE | green (D9) | microphone |
| FACE | yellow (D10) | face in front of the webcam |
| ERROR | red (D11) | blinks when something fails |

### Gesture mode

| Gesture | Command | Notes |
|---|---|---|
| Open palm (4 fingers up) | `PLAYPAUSE` | hold briefly, fires once per hold |
| Closed fist | `MUTE` | hold briefly, fires once per hold |
| Thumb tip touching index tip (pinch) | `VOLDOWN` | repeats while held |
| Thumb and index spread wide (L shape) | `VOLUP` | repeats while held |

The live finger count and pinch gap are drawn on the video (`GESTURE_DEBUG`) so you can tune the numbers.

### Voice mode (offline, Vosk)

| Say | Result |
|---|---|
| "volume up" / "louder", "volume down" / "quieter", "mute" | volume |
| "play", "pause", "next", "previous" | media keys |
| "scroll up", "scroll down", "zoom in", "zoom out", "click" | mouse / browser |
| "open chrome", "open notepad" | opens the app |
| "open youtube / google / gmail / github / whatsapp / maps" | opens the website |
| "search" → *(beep)* → say your query | Google search |
| "search youtube" → *(beep)* → say your query | YouTube search |
| "screenshot", "lock screen" | saves a PNG in `screenshots/` / locks Windows |

How the search works: the normal recogniser only knows the fixed phrases above. When it hears
"search" it switches to a full-vocabulary recogniser for **one sentence** (up to 8 s), then goes back.

### Face mode

| Action | Result |
|---|---|
| Move your head (nose tip) | moves the mouse cursor |
| Open your mouth and hold ~0.1 s | `CLICK` (once per opening) |
| Keep both eyes closed for 2 s | `LOCK` Windows |
| Leave the camera view for 10 s | `LOCK` Windows (arms after your face has been seen for 2 s, fires once) |

Face tracking uses MediaPipe blendshapes (`jawOpen`, `eyeBlink`), so it does not depend on how far you sit
from the camera. Live `jaw` / `eyes` values are drawn on the video for tuning.

### Repeat protection

After a command runs, the same command is ignored for **5 seconds** (`SLOW_COOLDOWN` in `main.py`).
Fast commands (volume, click, scroll, zoom, search) are exempt so you can slide the volume smoothly.

---

## 2. Hardware

| Part | Qty | Notes |
|---|---|---|
| Arduino Uno R3 (or clone with CH340) | 1 | |
| USB cable (data-capable) | 1 | charge-only cables will not work |
| LEDs: blue, green, yellow, red | 1 each | |
| 220 Ω resistors | 4 | one per LED |
| Push button | 1 | |
| 16x2 LCD **with I2C backpack** | 1 | the plain 16-pin LCD will not work without the backpack |
| Breadboard + jumper wires | 1 / ~15 | |

### Wiring

| Part | Arduino pin |
|---|---|
| Blue LED (+ 220 Ω) | D8 |
| Green LED (+ 220 Ω) | D9 |
| Yellow LED (+ 220 Ω) | D10 |
| Red LED (+ 220 Ω) | D11 |
| Button, other leg to GND | D2 (uses the internal pull-up, no resistor) |
| LCD GND | GND |
| LCD VCC | **5V** (not 3.3V) |
| LCD SDA | A4 |
| LCD SCL | A5 |

Each LED: Arduino pin → resistor → LED long leg (anode); LED short leg (cathode) → GND rail.
The LCD blue dial on the backpack is the contrast: turn it if the screen is lit but shows nothing.

---

## 3. Setup

**Requirements:** Windows 10/11, Python 3.10+, a webcam, a microphone, Arduino IDE 2.x.

1. **Get the code**
   ```
   git clone https://github.com/Plastic-water/arduino-project.git
   cd arduino-project
   ```
2. **Install Python packages**
   ```
   pip install -r requirements.txt
   ```
3. **Voice model**: the folder `models/vosk-model-small-en-us-0.15/` must exist
   (included in the repo; otherwise download it from https://alphacephei.com/vosk/models).
4. **Hand and face models**: `hand_landmarker.task` and `face_landmarker.task` are in the repo;
   they are downloaded automatically if missing.
5. **Arduino**
   - Install the library: *Tools → Manage Libraries → "LiquidCrystal I2C" by Frank de Brabander*.
   - Optional: upload `lcd_test/lcd_test.ino` first to check the screen alone.
   - Open `trisense_firmware/trisense_firmware.ino`, choose **Tools → Board → Arduino Uno** and the correct
     **Port** (the Arduino is usually *USB Serial Port* / *USB-SERIAL CH340*; ignore *Intel AMT - SOL*), then Upload.
   - Check that the LEDs chase one after another: the board is waiting for the PC.
   - **Close the Serial Monitor** afterwards. Only one program can use the COM port.
6. **Run**
   ```
   python main.py
   ```

### Keys in the camera window

| Key | Action |
|---|---|
| `M` | next mode (same as the Arduino button) |
| `ESC` | quit |

---

## 4. Files

| File | What it does |
|---|---|
| `main.py` | the controller: camera loop, mode switching, cooldowns, talks to every other module |
| `gesture_engine.py` | MediaPipe hand landmarks → gesture commands |
| `face_engine.py` | MediaPipe face landmarks/blendshapes → cursor, `CLICK`, `LOCK` |
| `voice_engine.py` | Vosk speech recognition → commands, site opening, spoken search |
| `actions.py` | turns a command name into a real PC action (`perform("VOLUP")`) |
| `arduino_link.py` | serial connection to the Arduino (auto-finds the port, reconnects) |
| `trisense_firmware/trisense_firmware.ino` | Arduino firmware: button, LEDs, LCD |
| `lcd_test/lcd_test.ino` | stand-alone LCD test |
| `old*_*.py` | backups of earlier versions |

Each engine can be tested alone: `python gesture_engine.py`, `python face_engine.py`, `python voice_engine.py`.

---

## 5. Message contract (Python ↔ Arduino)

Serial 9600 baud, text only, every message ends with `\n`, format `TYPE:VALUE`, ALL CAPS, no spaces
(use `_`), value at most 12 characters, at most ~10 messages per second.

**Python → Arduino**

| Message | Meaning |
|---|---|
| `MODE:GESTURE` / `MODE:VOICE` / `MODE:FACE` | active mode (mode LED + LCD line 1) |
| `CMD:<name>` | a command ran (LCD line 2, LED flickers), e.g. `CMD:VOLUP` |
| `ERR:<reason>` | something failed (red LED blinks 3 times, LCD shows it), e.g. `ERR:NO_MIC` |

**Arduino → Python**

| Message | Meaning |
|---|---|
| `READY` | the Arduino just booted; Python answers with the current `MODE:` |
| `BTN:PRESSED` | button pressed; Python switches to the next mode |

**Error reasons:** `NO_CAM`, `NO_MIC`, `NO_MODEL`, `NO_VOICE`, `ACTION_FAIL`.

**Command names:** `VOLUP VOLDOWN MUTE PLAYPAUSE NEXT PREV SCROLLUP SCROLLDOWN ZOOMIN ZOOMOUT CLICK LOCK
SCREENSHOT OPEN_CHROME OPEN_NOTEPAD OPEN_SITE SEARCH SEARCH_YT`.

**Test output of each module:** `[SOURCE] COMMAND`, for example `[GESTURE] VOLUP`.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| Upload fails: "programmer is not responding" | wrong port selected. Unplug/replug the Arduino and see which COM port appears in Device Manager |
| `[LINK] cannot open COMx` | Serial Monitor or another program is holding the port; close it |
| `Arduino: not connected` in the video | check the cable (needs data), the port, and that the firmware is uploaded |
| Button does nothing | use the `M` key to test the rest; check the button between D2 and GND and read the Serial Monitor for `BTN:PRESSED` (close it again afterwards) |
| LCD lit but blank | turn the blue contrast dial; check SDA/SCL on A4/A5; try address `0x3F` instead of `0x27` |
| LCD completely dark | 5V and GND wiring, or the I2C backpack is missing |
| `NO CAMERA` | another app is using the webcam, or it is disabled in Windows privacy settings |
| Pinch is read as fist | watch the on-screen *gap* value and adjust `PINCH_CLOSE_RATIO` in `gesture_engine.py` |
| Mouth click fires by accident / never | adjust `JAW_ON` / `JAW_OFF` in `face_engine.py` using the on-screen `jaw` value |
| Voice hears nothing | `DEVICE` in `voice_engine.py`; list microphones with `python -c "import sounddevice as sd; print(sd.query_devices())"` |
| Voice does not understand a site name | the small model may not know the word; try the other spelling ("you tube") |

## 7. Known issues

- Arduino button + LCD path is still being debugged (see latest commit); everything else works without the Arduino.
- Windows cannot be **unlocked** by software: after a `LOCK` you sign in normally.
- Swipe gestures (next / previous track by hand) are not included; use voice for `NEXT` / `PREV`.
- The small Vosk model has limited accuracy for free-form search queries.

## 8. Team

Gesture, face, Arduino firmware and main controller: Basavaraj. Voice module: Amit.

## 9. Possible extensions

Flask dashboard showing live mode and command history, swipe gestures, wake word for voice mode, custom macros.
