/*
  TriSense firmware (Arduino Uno)

  Wiring (same as your breadboard picture):
    LED blue   D8   gesture mode
    LED green  D9   voice mode
    LED yellow D10  face mode
    LED red    D11  error
    Button     D2 -> GND (INPUT_PULLUP, LOW = pressed)
    LCD I2C    SDA -> A4, SCL -> A5, VCC -> 5V, GND -> GND

  Library needed (Tools > Manage Libraries):  "LiquidCrystal I2C" by Frank de Brabander

  Serial: 9600 baud, text, newline-terminated, TYPE:VALUE
    PC -> Arduino   MODE:GESTURE | MODE:VOICE | MODE:FACE | CMD:xxx | ERR:xxx
    Arduino -> PC   READY | BTN:PRESSED
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ---------------- pins ----------------
const uint8_t LED_PINS[4] = {8, 9, 10, 11};  // 0 gesture, 1 voice, 2 face, 3 error
const uint8_t BTN_PIN = 2;

// ---------------- state ----------------
LiquidCrystal_I2C *lcd = nullptr;
bool lcdOk = false;

int8_t mode = -1;                 // -1 = no PC yet (chase animation), 0/1/2 = gesture/voice/face
unsigned long cmdFlashUntil = 0;  // mode LED goes dark briefly on every command

// error blink (non-blocking)
bool errOn = false;
uint8_t errToggles = 0;
unsigned long errNext = 0;

// boot chase animation
uint8_t chaseIdx = 0;
unsigned long chaseNext = 0;

// serial line buffer
char buf[32];
uint8_t bufLen = 0;
bool overflow = false;

// button debounce
bool btnRead = HIGH, btnStable = HIGH;
unsigned long btnChange = 0;

// ---------------- LCD helpers ----------------
void lcdLine(uint8_t row, const char *text) {
  if (!lcdOk) return;
  char out[17];
  snprintf(out, sizeof(out), "%-16s", text);  // pad / cut to exactly 16 chars
  lcd->setCursor(0, row);
  lcd->print(out);
}

void showLast(const char *val) {
  char line[24];
  snprintf(line, sizeof(line), "Last: %s", val);
  if (strlen(line) > 16) lcdLine(1, val);  // too long for "Last: " prefix, show just the command
  else lcdLine(1, line);
}

bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void initLcd() {
  Wire.begin();
  uint8_t addr = 0;
  // PCF8574 backpacks live at 0x20-0x27, PCF8574A ones at 0x38-0x3F
  // (0x27 and 0x3F are the usual defaults; solder pads A0-A2 change it)
  if (i2cPresent(0x27)) addr = 0x27;
  else if (i2cPresent(0x3F)) addr = 0x3F;
  else {
    for (uint8_t a = 0x20; a <= 0x3F && addr == 0; a++) {
      if (a > 0x27 && a < 0x38) continue;
      if (i2cPresent(a)) addr = a;
    }
  }
  if (addr == 0) {
    Serial.print(F("LCD: not found on I2C\n"));  // PC ignores unknown lines
    return;  // no LCD found: LEDs + serial still work
  }
  Serial.print(F("LCD: found at 0x"));
  Serial.print(addr, HEX);
  Serial.print('\n');
  lcd = new LiquidCrystal_I2C(addr, 16, 2);
  lcd->init();
  lcd->backlight();
  lcdOk = true;
}

// ---------------- LEDs ----------------
void startErrBlink() {
  errOn = true;
  errToggles = 5;  // on, off, on, off, on, off = 3 blinks
  errNext = millis() + 150;
}

void tickErr() {
  if (errToggles > 0 && millis() >= errNext) {
    errOn = !errOn;
    errToggles--;
    errNext = millis() + 150;
  }
}

void updateLeds() {
  unsigned long now = millis();
  if (mode < 0) {
    // waiting for the PC: lights run one by one (same as your blink test)
    if (now >= chaseNext) {
      chaseIdx = (chaseIdx + 1) % 4;
      chaseNext = now + 200;
    }
    for (uint8_t i = 0; i < 4; i++) digitalWrite(LED_PINS[i], i == chaseIdx);
    return;
  }
  for (uint8_t i = 0; i < 3; i++) {
    bool on = (i == mode) && (now >= cmdFlashUntil);
    digitalWrite(LED_PINS[i], on);
  }
  digitalWrite(LED_PINS[3], errOn);
}

// ---------------- message handling ----------------
void handleLine(char *line) {
  char *colon = strchr(line, ':');
  if (!colon) return;
  *colon = 0;
  const char *type = line;
  const char *val = colon + 1;

  if (strcmp(type, "MODE") == 0) {
    if (strcmp(val, "GESTURE") == 0) mode = 0;
    else if (strcmp(val, "VOICE") == 0) mode = 1;
    else if (strcmp(val, "FACE") == 0) mode = 2;
    else return;
    errToggles = 0;
    errOn = false;
    char l1[24];
    snprintf(l1, sizeof(l1), "MODE: %s", val);
    lcdLine(0, l1);
    lcdLine(1, "Last: ---");
  } else if (strcmp(type, "CMD") == 0) {
    showLast(val);
    cmdFlashUntil = millis() + 80;
  } else if (strcmp(type, "ERR") == 0) {
    char l2[24];
    snprintf(l2, sizeof(l2), "ERR: %s", val);
    if (strlen(l2) > 16) lcdLine(1, val);
    else lcdLine(1, l2);
    startErrBlink();
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (!overflow && bufLen > 0) {
        buf[bufLen] = 0;
        handleLine(buf);
      }
      bufLen = 0;
      overflow = false;
    } else if (bufLen < sizeof(buf) - 1) {
      buf[bufLen++] = c;
    } else {
      overflow = true;  // line too long: throw it away
    }
  }
}

void readButton() {
  bool r = digitalRead(BTN_PIN);
  if (r != btnRead) {
    btnRead = r;
    btnChange = millis();
  }
  if (millis() - btnChange > 40 && r != btnStable) {
    btnStable = r;
    if (r == LOW) Serial.print(F("BTN:PRESSED\n"));
  }
}

// ---------------- Arduino entry points ----------------
void setup() {
  for (uint8_t i = 0; i < 4; i++) pinMode(LED_PINS[i], OUTPUT);
  pinMode(BTN_PIN, INPUT_PULLUP);
  Serial.begin(9600);
  initLcd();
  lcdLine(0, "TriSense");
  lcdLine(1, "Waiting for PC..");
  Serial.print(F("READY\n"));
}

void loop() {
  readSerial();
  readButton();
  tickErr();
  updateLeds();
}
