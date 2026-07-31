#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>

const uint8_t TFT_CS = 9;
const uint8_t TFT_DC = 8;
const uint8_t TFT_RST = 7;
const uint8_t TFT_MOSI = 11;
const uint8_t TFT_SCLK = 13;

// Software SPI is deliberately used here to remove hardware-SPI setup from
// the diagnosis and to clock the long jumper wires very slowly.
Adafruit_ST7789 tft(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println(F("Starting TFT-only diagnostic"));

  pinMode(TFT_RST, OUTPUT);
  digitalWrite(TFT_RST, HIGH);
  delay(20);
  digitalWrite(TFT_RST, LOW);
  delay(20);
  digitalWrite(TFT_RST, HIGH);
  delay(120);

  tft.init(240, 240);
  tft.setRotation(2);
  tft.invertDisplay(false);
  tft.setTextWrap(false);

  // Draw once and then leave the display completely untouched.
  tft.fillScreen(ST77XX_BLACK);
  tft.fillRect(0, 0, 120, 120, ST77XX_RED);
  tft.fillRect(120, 0, 120, 120, ST77XX_GREEN);
  tft.fillRect(0, 120, 120, 120, ST77XX_BLUE);
  tft.fillRect(120, 120, 120, 120, ST77XX_WHITE);

  tft.fillRoundRect(35, 92, 170, 56, 8, ST77XX_BLACK);
  tft.drawRoundRect(35, 92, 170, 56, 8, ST77XX_YELLOW);
  tft.setTextColor(ST77XX_YELLOW);
  tft.setTextSize(2);
  tft.setCursor(58, 103);
  tft.print(F("TFT TEST"));
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(55, 128);
  tft.print(F("STATIC - NO BLINK"));

  Serial.println(F("Static test image drawn; loop does not redraw"));
}

void loop() {
  delay(1000);
}
