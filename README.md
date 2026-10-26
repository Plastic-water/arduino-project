TRISENSE: MESSAGE CONTRACT (all 4 must follow exactly)

SERIAL SETTINGS
- 9600 baud, text only, every message ends with a newline (\n)
- Format: TYPE:VALUE
- ALL CAPS, no spaces (use _ instead), VALUE max 12 characters
- Only ONE program can use the COM port at a time
  (close Arduino Serial Monitor before running Python)

PYTHON -> ARDUINO
MODE:GESTURE   gesture mode active (blue LED)
MODE:VOICE     voice mode active (green LED)
MODE:FACE      face mode active (yellow LED)
CMD:<name>     a command was executed, shown on LCD line 2 (e.g. CMD:VOLUP)
ERR:<reason>   something failed, red LED + LCD (e.g. ERR:NO_MIC, ERR:NO_CAM)

ARDUINO -> PYTHON
READY          Arduino just booted, Python then sends MODE:GESTURE
BTN:PRESSED    button pressed, Python switches to the next mode

LCD LAYOUT (16x2)
Line 1: MODE: VOICE
Line 2: Last: VOLUP

OFFICIAL COMMAND NAMES (use these exact names, don't invent new ones)
Shared:   VOLUP  VOLDOWN  MUTE  PLAYPAUSE  NEXT  PREV
Gesture:  SCROLLUP  SCROLLDOWN  ZOOMIN  ZOOMOUT
Voice:    OPEN_CHROME  OPEN_NOTEPAD  SCREENSHOT  LOCK
Face:     CLICK  LOCK  (cursor movement is NOT sent to the Arduino, too many messages)

MODULE TEST OUTPUT (what A, B and C print while testing alone)
[GESTURE] VOLUP
[VOICE] OPEN_CHROME
[FACE] CLICK
Format: [SOURCE] COMMAND. This is what the main program will receive.

RULES
1. Send only events (something happened), never a constant stream.
2. Add a cooldown of about 0.5 s per command so one gesture doesn't fire 10 times.
3. Send at most about 10 messages per second to the Arduino.
4. Nobody changes the names or format without telling everyone.



help me with my part. Context so far (planned with another AI):

PROJECT: "TriSense: A Gesture, Voice and Face-Based Contactless PC Control System with Arduino Feedback"
COURSE RULES: IA-2 project-based learning, Arduino or Raspberry Pi based working model, group of up to 4(tho only 2 people will be doing the real work),  there is a viva and demo.
SKILL LEVEL: beginner on hardware (no soldering, never used a breadboard), comfortable with Python/C++. Keep explanations simple and go step by step.

HOW IT WORKS
- The laptop does all the heavy work: Python + OpenCV + MediaPipe (hand gestures, face/head tracking, blink click), Vosk (offline voice recognition), pyautogui (volume, scroll, screenshot, lock), screen-brightness-control, Flask web dashboard (live command log, mode toggles).
- Arduino Uno (clone, CH340 USB chip) is a physical control panel, connected by USB serial at 9600 baud: a button cycles modes (Gesture/Voice/Face), 4 LEDs show the mode and errors, a 16x2 I2C LCD shows the mode and last command.
- Data flows both ways: Python -> Arduino (status), Arduino -> Python (button press).

TEAM SPLIT
A: gesture engine | B: voice engine | A: face/head tracking | a or c: Arduino firmware + serial bridge + Flask dashboard.
Only D needs the Arduino. A, B and C develop on the laptop alone and print their detections.

MESSAGE CONTRACT (the whole project depends on this, do NOT change it)
- 9600 baud, newline-terminated, TYPE:VALUE, ALL CAPS, no spaces, value max 12 chars.
- Python -> Arduino: MODE:GESTURE | MODE:VOICE | MODE:FACE | CMD:<name> | ERR:<reason>
- Arduino -> Python: READY | BTN:PRESSED
- Command names: VOLUP VOLDOWN MUTE PLAYPAUSE NEXT PREV SCROLLUP SCROLLDOWN ZOOMIN ZOOMOUT OPEN_CHROME OPEN_NOTEPAD SCREENSHOT LOCK CLICK
- While testing alone, each module prints: [SOURCE] COMMAND (e.g. [GESTURE] VOLUP, [VOICE] OPEN_CHROME, [FACE] CLICK)
- Send events only (not streams), 0.5 s cooldown per command, max about 10 messages/s.
- LCD: line 1 "MODE: VOICE", line 2 "Last: VOLUP".

ARDUINO WIRING (breadboard, no soldering)
LCD I2C: GND->GND, VCC->5V, SDA->A4, SCL->A5 (address 0x27, or 0x3F if blank; library LiquidCrystal_I2C)
LEDs each via 220 ohm resistor to GND: blue D8 (gesture), green D9 (voice), yellow D10 (face), red D11 (error)
Button: D2 to GND, use INPUT_PULLUP (LOW = pressed), debounce in code.

HARDWARE STATUS
Done: Arduino IDE 2.3.10 installed, board tested on a Windows Dell laptop with the Blink example. Lesson learned: COM3 was the laptop's internal Intel port, the Arduino was COM6 (check Device Manager before selecting a port).
Still to buy (about Rs 330-555): 16x2 I2C LCD, 4 LEDs, 220 ohm resistors, push buttons, 830-point breadboard, male-male and male-female jumper wires.

ROADMAP
0. Set up GitHub/shared folder, install libraries, agree on contract (done: this contract)
1. Each module works alone and prints [SOURCE] COMMAND; D does the serial "hello" test, then LEDs, button, LCD one at a time
2. Main controller combines modules, performs PC actions, handles mode switching
3. Connect the Arduino: button -> mode change -> LCD/LED update
4. Flask dashboard (command log, mode toggles)
5. Test and tune (lighting, noise, false triggers)
6. Freeze features, report, backup demo video, viva practice

WHAT I WANT NOW
I am Person [A] Help me build and test my module step by step: first a minimal working version, then improve it. Use exactly the message contract above. Give complete runnable code with install commands for Windows, and tell me how to test each step before the next.


