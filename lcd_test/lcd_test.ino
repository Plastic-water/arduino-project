/*
  LCD test: nothing else, just the screen.
  Wiring: GND->GND, VCC->5V (NOT 3.3V), SDA->A4, SCL->A5
  Library: "LiquidCrystal I2C" by Frank de Brabander
  Sweep the blue contrast dial while this runs. The counter keeps changing,
  so you will see it update as soon as the contrast is right.
*/
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);   // change to 0x3F if the scanner said so
unsigned long n = 0;

void setup() {
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Hello TriSense");
}      

void loop() {
  lcd.setCursor(0, 1);
  lcd.print("count: ");
  lcd.print(n++);
  lcd.print("    ");
  delay(500);
}
