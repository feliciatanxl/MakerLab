# Spotify Matrix Arcade

This is a separate ESP32-S3 project. The original `R4-Spotify` folder is not
modified.

At startup, the 240x240 TFT offers two choices:

- **Spotify**: the existing live player, album artwork, synchronized lyrics,
  and animated MAX7219 equalizer.
- **Matrix**: a falling-block game on the four vertically stacked 8x8 panels.

The game can be controlled with the analogue joystick, the pictured four-key
board, or both at the same time.

## Wiring

All modules must share **one common ground**. The MAX7219 tower should use a
regulated external 5 V supply; connect that supply's GND to ESP32 GND. Do not
power four MAX7219 panels from the ESP32 3V3 pin.

### ST7789 240x240 TFT

| TFT pin | ESP32-S3 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SCL / SCK | GPIO12 |
| SDA / MOSI | GPIO11 |
| CS | GPIO10 |
| DC | GPIO9 |
| RST / RES | GPIO8 |
| BL / LED | 3V3 |

### Four-panel MAX7219 matrix

Use the matrix connector marked **IN**.

| Matrix pin | ESP32-S3 / supply |
| --- | --- |
| VCC | Regulated external 5 V |
| GND | External supply GND and ESP32 GND |
| DIN | GPIO4 |
| CLK | GPIO5 |
| CS / LOAD | GPIO6 |

Start with matrix intensity `1` in the sketch. Four panels can draw much more
current when many LEDs are on.

### Analogue joystick

The pictured joystick labels appear to be `GND`, `+5V`, `VRx`, `VRy`, and
`SW`. Power it from **3V3**, not 5 V, so its analogue outputs cannot exceed the
ESP32's 3.3 V input range.

| Joystick pin | ESP32-S3 |
| --- | --- |
| GND | GND |
| +5V / VCC | 3V3 |
| VRx | GPIO1 |
| VRy | GPIO2 |
| SW | GPIO3 |

If movement is reversed, change `JOYSTICK_X_REVERSED` or
`JOYSTICK_Y_REVERSED` near the top of the sketch.

### Four-key board

The photographed board has six connector pins: normally GND, VCC, and one
signal for each key. Confirm the tiny labels printed beside your particular
board before applying power; board pin order varies.

| Key-board signal | ESP32-S3 |
| --- | --- |
| GND | GND |
| VCC | 3V3 |
| S1 / K1 / left | GPIO13 |
| S2 / K2 / right | GPIO14 |
| S3 / K3 / action | GPIO15 |
| S4 / K4 / down | GPIO16 |

The sketch expects a pressed key to pull its signal **LOW** and enables the
ESP32's internal pull-ups. If this board outputs HIGH when pressed, invert the
four digital reads in `readInputEvents()`.

### Buzzer module

The pictured buzzer board is a three-pin module marked VCC, I/O (or S), and
GND.

| Buzzer pin | ESP32-S3 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| I/O / S | GPIO17 |

The default `ACTIVE_BUZZER_MODULE = true` matches the usual active buzzer
module. Set it to `false` for a passive piezo buzzer.

## Controls

| Screen | Joystick | Four-key board |
| --- | --- | --- |
| Menu | Move to choose; press SW | S1/S2 choose; S3 opens |
| Game | Left/right move, down drops, SW rotates | S1/S2 move, S4 drops, S3 rotates |
| Return to menu | Hold SW for 1.2 seconds | Press S1 and S2 together |
| Spotify quick return | Hold SW | S4 also returns |

## Arduino setup

Use **ESP32S3 Dev Module** or **ESP32-S3 DevKitC-1** and select **Huge APP
(3MB No OTA/1MB SPIFFS)**. Install these libraries through Arduino IDE's
Library Manager:

- Adafruit GFX Library
- Adafruit ST7735 and ST7789 Library
- ArduinoJson 7
- JPEGDecoder by Bodmer
- U8g2_for_Adafruit_GFX

Open `Spotify_Matrix_Arcade.ino`, select the correct board and serial port, and
upload it.

The local `arduino_secrets.h` was copied from the working Spotify project so
the new project can use the same account without changing the original. It is
ignored by Git. If the credentials need to be set again, copy
`arduino_secrets.example.h` to `arduino_secrets.h`, fill in the Wi-Fi, Spotify
client ID and client secret, then run `Get-Spotify-Refresh-Token.cmd`. The
helper writes the refresh token into this new project's secrets file only.

## Matrix orientation adjustments

If the game is upside down or mirrored, change only these constants near the
top of the sketch:

```cpp
const bool MATRIX_REVERSE_STACK = false;
const bool MATRIX_ROW_ZERO_IS_TOP = true;
const bool MATRIX_MIRROR_HORIZONTAL = false;
```

Change one option at a time, upload, and retest.
