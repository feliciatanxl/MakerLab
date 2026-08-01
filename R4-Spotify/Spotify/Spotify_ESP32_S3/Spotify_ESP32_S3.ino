/*
  Spotify live player for ESP32-S3 + 240x240 ST7789

  What this sketch does
  ---------------------
  - Polls Spotify for the account's currently playing track.
  - Shows the title, artist, album art, play state and progress on one screen.
  - Gets time-synchronised lyrics from LRCLIB and follows the current line.

  What it cannot do
  -----------------
  Spotify does not provide lyrics. LRCLIB is therefore used for synchronized lyrics.

  Install these libraries with Arduino IDE > Library Manager:
    - Adafruit GFX Library
    - Adafruit ST7735 and ST7789 Library
    - ArduinoJson (version 7)
    - JPEGDecoder by Bodmer
    - U8g2_for_Adafruit_GFX

  Board: ESP32S3 Dev Module / ESP32-S3 DevKitC-1
  Arduino IDE: Tools > Partition Scheme > Huge APP (3MB No OTA/1MB SPIFFS)
  The larger partition is required for expanded Chinese/Korean/Thai fonts.

  TFT wiring (software SPI; 3.3 V logic)
    TFT VCC -> 3V3
    TFT GND -> GND
    TFT SCL -> GPIO12
    TFT SDA -> GPIO11
    TFT CS  -> GPIO10
    TFT DC  -> GPIO9
    TFT RST -> GPIO8
    TFT BL  -> 3V3

  Four-panel MAX7219 matrix (use the connector marked IN)
    Matrix VCC -> regulated 5 V supply
    Matrix GND -> supply GND and ESP32 GND (all grounds connected)
    Matrix DIN -> GPIO4
    Matrix CLK -> GPIO5
    Matrix CS  -> GPIO6
  Start at low brightness. Four panels can draw substantial current, so an
  external 5 V supply is recommended instead of the ESP32 3V3 pin.

  Spotify setup
  -------------
  1. Create an app at https://developer.spotify.com/dashboard
  2. Add this exact redirect URI: http://127.0.0.1:8888/callback
  3. Put the app credentials in arduino_secrets.h, then run
       Get-Spotify-Refresh-Token.cmd to complete authorization.
  4. arduino_secrets.h is ignored by Git; never publish your real credentials.

  Spotify refresh tokens for dashboard apps can expire. If the screen reports an
  authentication error after working previously, complete the OAuth flow again.
*/

#include <SPI.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <U8g2_for_Adafruit_GFX.h>
#include <ArduinoJson.h>
#include <JPEGDecoder.h>
#include <ctype.h>
#include <stdlib.h>
#include "cjk16_font.h"
#include "../arduino_secrets.h"

// =============================================================================
// User configuration
// =============================================================================

const char WIFI_SSID[] = SECRET_WIFI_SSID;
const char WIFI_PASSWORD[] = SECRET_WIFI_PASSWORD;

const char SPOTIFY_CLIENT_ID[] = SECRET_SPOTIFY_CLIENT_ID;
const char SPOTIFY_CLIENT_SECRET[] = SECRET_SPOTIFY_CLIENT_SECRET;
const char SPOTIFY_REFRESH_TOKEN[] = SECRET_SPOTIFY_REFRESH_TOKEN;

// LRCLIB asks clients to identify themselves.
const char LRCLIB_USER_AGENT[] = SECRET_LRCLIB_USER_AGENT;

// Set to false if the display colours are inverted on your ST7789 module.
const bool TFT_INVERT = false;
// Use 2 to turn the displayed picture 180 degrees.
const uint8_t TFT_ROTATION = 2;

// =============================================================================
// Hardware and layout
// =============================================================================

const uint8_t TFT_CS = 10;
const uint8_t TFT_DC = 9;
const uint8_t TFT_RST = 8;
const uint8_t TFT_MOSI = 11;
const uint8_t TFT_SCLK = 12;

const uint8_t MATRIX_DIN = 4;
const uint8_t MATRIX_CLK = 5;
const uint8_t MATRIX_CS = 6;
const uint8_t MATRIX_DEVICE_COUNT = 4;
const uint8_t MATRIX_INTENSITY = 1;  // 0..15; keep low when powered from USB.
// Change both vertical options if your particular chain grows from top to
// bottom. MATRIX_MIRROR_HORIZONTAL only swaps left and right.
const bool MATRIX_REVERSE_STACK = false;
const bool MATRIX_ROW_ZERO_IS_TOP = true;
const bool MATRIX_MIRROR_HORIZONTAL = false;

// Software SPI matches the stable TFT diagnostic and is more tolerant of
// breadboard wiring while Wi-Fi/HTTPS is active.
Adafruit_ST7789 tft(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);
U8G2_FOR_ADAFRUIT_GFX unicodeText;
WiFiClientSecure secureClient;

const int16_t SCREEN_WIDTH = 240;
const int16_t SCREEN_HEIGHT = 240;

const int16_t ART_FRAME_X = 7;
const int16_t ART_FRAME_Y = 20;
const int16_t ART_FRAME_SIZE = 82;
const int16_t ART_INNER_SIZE = 78;

const int16_t PROGRESS_X = 8;
const int16_t PROGRESS_Y = 106;
const int16_t PROGRESS_WIDTH = 224;
const int16_t PROGRESS_HEIGHT = 5;

const uint16_t SPOTIFY_GREEN = 0x1DAB;
const uint16_t APP_BACKGROUND = 0x0021;
const uint16_t TRACK_CARD = 0x0883;
const uint16_t LYRICS_CARD = 0x1065;
const uint16_t CARD_BORDER = 0x294A;
const uint16_t MUTED_TEXT = 0x9CD3;
const uint16_t DIM_TEXT = 0x4A69;
const uint16_t PANEL_GREY = 0x18C3;

const int16_t LYRICS_PANEL_X = 4;
const int16_t LYRICS_PANEL_Y = 125;
const int16_t LYRICS_PANEL_WIDTH = 232;
const int16_t LYRICS_PANEL_HEIGHT = 111;

// The smallest Spotify artwork is normally 64x64 and comfortably below 8 KB.
// Larger downloads are rejected to protect the UNO R4's 32 KB SRAM.
const size_t MAX_ALBUM_JPEG_BYTES = 8 * 1024;

// =============================================================================
// Timing and state
// =============================================================================

const uint32_t SPOTIFY_POLL_MS = 5000;
// Progress redraws are relatively expensive on software SPI. Lyrics are
// checked frequently but drawLyrics() writes only when the active line changes.
const uint32_t PROGRESS_UPDATE_MS = 33;  // About 30 frames per second.
const uint32_t LYRIC_CHECK_MS = 100;
const uint32_t MATRIX_UPDATE_MS = 45;  // About 22 animation frames per second.
const uint32_t MATRIX_TARGET_MS = 90;
const uint32_t WIFI_RETRY_MS = 10000;
const uint32_t HTTP_TIMEOUT_MS = 10000;
const uint32_t AUTH_ERROR_RETRY_MS = 60000;

struct TrackInfo {
  String id;
  String title;
  String artist;
  String album;
  String artUrl;
  uint32_t durationMs;
  uint32_t progressMs;
  uint32_t snapshotAtMs;
  bool isPlaying;
};

TrackInfo currentTrack;
bool hasCurrentTrack = false;

String spotifyAccessToken;
uint32_t tokenRefreshAtMs = 0;
uint32_t nextSpotifyPollAtMs = 0;
uint32_t nextWiFiAttemptAtMs = 0;
uint32_t lastProgressUpdateAtMs = 0;
uint32_t lastLyricCheckAtMs = 0;
uint32_t lastMatrixUpdateAtMs = 0;
int16_t lastProgressFilled = -1;
uint8_t lastProgressFraction = 255;
uint32_t lastProgressSecond = UINT32_MAX;
bool spotifyAuthErrorShown = false;
bool matrixIsLit = false;
uint8_t matrixRows[MATRIX_DEVICE_COUNT][8] = {};
uint8_t matrixBarHeight[8] = {};
uint8_t matrixTargetHeight[8] = {};
uint32_t nextMatrixTargetAtMs = 0;

// =============================================================================
// Lyrics state
// =============================================================================

const size_t MAX_LYRIC_LINES = 64;
// This is a byte limit. UTF-8 Asian characters normally use three bytes.
const size_t MAX_LYRIC_CHARS = 72;

struct LyricLine {
  uint32_t atMs;
  char text[MAX_LYRIC_CHARS + 1];
};

LyricLine lyricLines[MAX_LYRIC_LINES];
size_t lyricLineCount = 0;
int lastDrawnLyric = -999;
String lyricStatus = "Waiting for a track";

void drawUtf8FittedCenteredLine(
  const char* text,
  int16_t boxX,
  int16_t baselineY,
  int16_t boxWidth,
  uint16_t colour,
  bool bold = false
);

// =============================================================================
// Small utilities
// =============================================================================

bool timeReached(uint32_t deadline) {
  return (int32_t)(millis() - deadline) >= 0;
}

bool isPlaceholder(const char* value) {
  return value == nullptr || value[0] == '\0' || strstr(value, "YOUR_") != nullptr;
}

bool configurationIsReady() {
  return !isPlaceholder(WIFI_SSID) &&
         !isPlaceholder(SPOTIFY_CLIENT_ID) &&
         !isPlaceholder(SPOTIFY_CLIENT_SECRET) &&
         !isPlaceholder(SPOTIFY_REFRESH_TOKEN);
}

void copyDisplayText(
  char* destination,
  size_t destinationSize,
  const char* source,
  size_t sourceLength
) {
  if (destinationSize == 0) return;

  size_t out = 0;
  size_t in = 0;

  while (in < sourceLength && out + 1 < destinationSize) {
    uint8_t c = (uint8_t)source[in];

    if (c >= 32 && c <= 126) {
      destination[out++] = (char)c;
      in++;
    } else if (c == '\t') {
      destination[out++] = ' ';
      in++;
    } else if (c >= 0xC2) {
      // The built-in Adafruit font is ASCII-only. Use one '?' per UTF-8 glyph.
      destination[out++] = '?';
      in++;
      while (in < sourceLength && (((uint8_t)source[in] & 0xC0) == 0x80)) in++;
    } else {
      in++;
    }
  }

  while (out > 0 && destination[out - 1] == ' ') out--;
  destination[out] = '\0';
}

void stringToDisplayText(const String& source, char* destination, size_t size) {
  copyDisplayText(destination, size, source.c_str(), source.length());
}

void copyUtf8Text(
  char* destination,
  size_t size,
  const char* source,
  size_t sourceLength
) {
  if (size == 0) return;

  size_t in = 0;
  size_t out = 0;
  while (in < sourceLength && out + 1 < size) {
    uint8_t first = (uint8_t)source[in];
    size_t sequenceLength = 1;
    if ((first & 0xE0) == 0xC0) sequenceLength = 2;
    else if ((first & 0xF0) == 0xE0) sequenceLength = 3;
    else if ((first & 0xF8) == 0xF0) sequenceLength = 4;

    if (in + sequenceLength > sourceLength ||
        out + sequenceLength >= size) {
      break;
    }

    bool valid = true;
    for (size_t i = 1; i < sequenceLength; i++) {
      if (((uint8_t)source[in + i] & 0xC0) != 0x80) {
        valid = false;
        break;
      }
    }
    if (!valid) {
      in++;
      continue;
    }

    memcpy(destination + out, source + in, sequenceLength);
    out += sequenceLength;
    in += sequenceLength;
  }

  while (out > 0 && destination[out - 1] == ' ') out--;
  destination[out] = '\0';
}

String urlEncode(const String& value) {
  const char hex[] = "0123456789ABCDEF";
  String encoded;
  encoded.reserve(value.length() * 2);

  for (size_t i = 0; i < value.length(); i++) {
    uint8_t c = (uint8_t)value[i];
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
      encoded += (char)c;
    } else {
      encoded += '%';
      encoded += hex[c >> 4];
      encoded += hex[c & 0x0F];
    }
  }

  return encoded;
}

String base64Encode(const String& input) {
  const char alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String output;
  output.reserve(((input.length() + 2) / 3) * 4);

  size_t i = 0;
  while (i < input.length()) {
    uint32_t value = (uint8_t)input[i++] << 16;
    bool hasSecond = i < input.length();
    if (hasSecond) value |= (uint8_t)input[i++] << 8;
    bool hasThird = i < input.length();
    if (hasThird) value |= (uint8_t)input[i++];

    output += alphabet[(value >> 18) & 0x3F];
    output += alphabet[(value >> 12) & 0x3F];
    output += hasSecond ? alphabet[(value >> 6) & 0x3F] : '=';
    output += hasThird ? alphabet[value & 0x3F] : '=';
  }

  return output;
}

void formatTime(uint32_t milliseconds, char* output, size_t outputSize) {
  uint32_t totalSeconds = milliseconds / 1000;
  uint32_t minutes = totalSeconds / 60;
  uint32_t seconds = totalSeconds % 60;
  snprintf(output, outputSize, "%lu:%02lu",
           (unsigned long)minutes, (unsigned long)seconds);
}

// =============================================================================
// Minimal HTTP body stream, including chunked-transfer decoding
// =============================================================================

struct HttpResponse {
  int status = 0;
  long contentLength = -1;
  bool chunked = false;
  int retryAfterSeconds = 0;
  String location;
  String contentType;
};

// Explicit declaration prevents Arduino's .ino preprocessor from placing its
// generated prototype above the HttpResponse type definition.
bool readHttpResponseHeaders(WiFiClientSecure& client, HttpResponse& response);

bool readNetworkLine(WiFiClientSecure& client, String& line) {
  line = "";
  line.reserve(160);
  uint32_t lastActivity = millis();

  while ((uint32_t)(millis() - lastActivity) < HTTP_TIMEOUT_MS) {
    while (client.available()) {
      char c = (char)client.read();
      lastActivity = millis();
      if (c == '\n') return true;
      if (c != '\r' && line.length() < 512) line += c;
    }

    if (!client.connected() && !client.available()) return line.length() > 0;
    delay(1);
  }

  return false;
}

bool readHttpResponseHeaders(WiFiClientSecure& client, HttpResponse& response) {
  String line;
  if (!readNetworkLine(client, line)) return false;

  int firstSpace = line.indexOf(' ');
  if (firstSpace < 0) return false;
  response.status = line.substring(firstSpace + 1).toInt();

  while (readNetworkLine(client, line)) {
    if (line.length() == 0) return true;

    int colon = line.indexOf(':');
    if (colon < 0) continue;

    String name = line.substring(0, colon);
    String value = line.substring(colon + 1);
    name.toLowerCase();
    value.trim();

    if (name == "content-length") {
      response.contentLength = value.toInt();
    } else if (name == "transfer-encoding") {
      value.toLowerCase();
      response.chunked = value.indexOf("chunked") >= 0;
    } else if (name == "retry-after") {
      response.retryAfterSeconds = value.toInt();
    } else if (name == "location") {
      response.location = value;
    } else if (name == "content-type") {
      response.contentType = value;
    }
  }

  return false;
}

class HttpBodyStream : public Stream {
 public:
  HttpBodyStream(WiFiClientSecure& client, long contentLength, bool chunked)
    : client_(client), remaining_(contentLength), chunked_(chunked) {}

  int available() override {
    if (cached_ >= 0) return 1;
    if (finished_ || (!chunked_ && remaining_ == 0)) return 0;
    return client_.available();
  }

  int read() override {
    if (cached_ >= 0) {
      int value = cached_;
      cached_ = -1;
      return value;
    }
    return readInternal();
  }

  int peek() override {
    if (cached_ < 0) cached_ = readInternal();
    return cached_;
  }

  void flush() override {}
  size_t write(uint8_t) override { return 0; }
  using Print::write;

 private:
  WiFiClientSecure& client_;
  long remaining_;
  bool chunked_;
  bool finished_ = false;
  bool consumeChunkCrLf_ = false;
  uint32_t chunkRemaining_ = 0;
  int cached_ = -1;

  int readClientByte() {
    uint32_t lastActivity = millis();
    while ((uint32_t)(millis() - lastActivity) < HTTP_TIMEOUT_MS) {
      if (client_.available()) return client_.read();
      if (!client_.connected()) return -1;
      delay(1);
    }
    return -1;
  }

  bool beginNextChunk() {
    if (consumeChunkCrLf_) {
      if (readClientByte() < 0 || readClientByte() < 0) return false;
      consumeChunkCrLf_ = false;
    }

    String line;
    line.reserve(16);
    while (true) {
      int value = readClientByte();
      if (value < 0) return false;
      if (value == '\n') break;
      if (value != '\r' && line.length() < 32) line += (char)value;
    }

    int extension = line.indexOf(';');
    if (extension >= 0) line.remove(extension);
    chunkRemaining_ = strtoul(line.c_str(), nullptr, 16);

    if (chunkRemaining_ == 0) {
      // Consume optional trailer headers.
      do {
        line = "";
        while (true) {
          int value = readClientByte();
          if (value < 0) break;
          if (value == '\n') break;
          if (value != '\r' && line.length() < 128) line += (char)value;
        }
      } while (line.length() > 0);

      finished_ = true;
      return false;
    }

    return true;
  }

  int readInternal() {
    if (finished_) return -1;

    if (chunked_) {
      if (chunkRemaining_ == 0 && !beginNextChunk()) return -1;

      int value = readClientByte();
      if (value < 0) {
        finished_ = true;
        return -1;
      }

      chunkRemaining_--;
      if (chunkRemaining_ == 0) consumeChunkCrLf_ = true;
      return value;
    }

    if (remaining_ == 0) return -1;
    int value = readClientByte();
    if (value < 0) return -1;
    if (remaining_ > 0) remaining_--;
    return value;
  }
};

bool openHttps(const char* host) {
  secureClient.stop();
  delay(10);
  secureClient.setTimeout(HTTP_TIMEOUT_MS);

  Serial.print(F("HTTPS -> "));
  Serial.println(host);
  return secureClient.connect(host, 443) == 1;
}

// =============================================================================
// Display helpers
// =============================================================================

void drawCenteredLine(
  const char* text,
  int16_t boxX,
  int16_t y,
  int16_t boxWidth,
  uint8_t textSize,
  uint16_t colour
) {
  int16_t x1, y1;
  uint16_t width, height;
  tft.setTextSize(textSize);
  tft.setTextWrap(false);
  tft.setTextColor(colour);
  tft.getTextBounds(text, 0, y, &x1, &y1, &width, &height);
  int16_t x = boxX + (boxWidth - (int16_t)width) / 2;
  if (x < boxX) x = boxX;
  tft.setCursor(x, y);
  tft.print(text);
}

void drawWrappedCentered(
  const char* text,
  int16_t boxX,
  int16_t y,
  int16_t boxWidth,
  uint8_t textSize,
  uint16_t colour,
  uint8_t maxLines
) {
  if (text == nullptr || text[0] == '\0') return;

  const size_t maxChars = max((int)1, boxWidth / (6 * textSize));
  const size_t textLength = strlen(text);
  size_t position = 0;

  for (uint8_t lineNumber = 0;
       lineNumber < maxLines && position < textLength;
       lineNumber++) {
    while (position < textLength && text[position] == ' ') position++;
    if (position >= textLength) break;

    size_t remaining = textLength - position;
    size_t take = min(maxChars, remaining);

    if (take < remaining) {
      size_t wordBreak = take;
      while (wordBreak > 0 && text[position + wordBreak] != ' ') wordBreak--;
      if (wordBreak > 0) take = wordBreak;
    }

    char line[64];
    size_t copyLength = min(take, sizeof(line) - 1);
    memcpy(line, text + position, copyLength);
    line[copyLength] = '\0';
    while (copyLength > 0 && line[copyLength - 1] == ' ') {
      line[--copyLength] = '\0';
    }

    bool truncated = (lineNumber == maxLines - 1) &&
                     (position + take < textLength);
    if (truncated && copyLength >= 3) {
      line[copyLength - 3] = '.';
      line[copyLength - 2] = '.';
      line[copyLength - 1] = '.';
    }

    drawCenteredLine(
      line,
      boxX,
      y + lineNumber * (8 * textSize),
      boxWidth,
      textSize,
      colour
    );

    position += take;
  }
}

void drawStatusScreen(const char* heading, const char* detail) {
  tft.fillScreen(ST77XX_BLACK);
  tft.fillCircle(120, 62, 34, SPOTIFY_GREEN);
  tft.fillCircle(109, 57, 3, ST77XX_BLACK);
  tft.fillCircle(120, 52, 3, ST77XX_BLACK);
  tft.fillCircle(131, 57, 3, ST77XX_BLACK);
  tft.drawFastHLine(101, 68, 38, ST77XX_BLACK);

  drawCenteredLine(heading, 8, 111, 224, 2, ST77XX_WHITE);
  drawWrappedCentered(detail, 20, 145, 200, 1, MUTED_TEXT, 5);
}

void runTftColourTest() {
  tft.fillScreen(ST77XX_RED);
  delay(300);
  tft.fillScreen(ST77XX_GREEN);
  delay(300);
  tft.fillScreen(ST77XX_BLUE);
  delay(300);
  tft.fillScreen(ST77XX_BLACK);
}

void drawAlbumPlaceholder() {
  tft.fillRect(
    ART_FRAME_X + 2,
    ART_FRAME_Y + 2,
    ART_INNER_SIZE,
    ART_INNER_SIZE,
    PANEL_GREY
  );

  tft.fillCircle(ART_FRAME_X + 42, ART_FRAME_Y + 42, 28, SPOTIFY_GREEN);
  tft.drawLine(ART_FRAME_X + 34, ART_FRAME_Y + 30,
               ART_FRAME_X + 34, ART_FRAME_Y + 52, ST77XX_WHITE);
  tft.drawLine(ART_FRAME_X + 35, ART_FRAME_Y + 30,
               ART_FRAME_X + 56, ART_FRAME_Y + 25, ST77XX_WHITE);
  tft.drawLine(ART_FRAME_X + 56, ART_FRAME_Y + 25,
               ART_FRAME_X + 56, ART_FRAME_Y + 47, ST77XX_WHITE);
  tft.fillCircle(ART_FRAME_X + 29, ART_FRAME_Y + 54, 6, ST77XX_WHITE);
  tft.fillCircle(ART_FRAME_X + 51, ART_FRAME_Y + 49, 6, ST77XX_WHITE);
}

void drawPlaybackState() {
  tft.fillRect(208, 2, 29, 14, APP_BACKGROUND);
  if (!hasCurrentTrack) return;

  if (currentTrack.isPlaying) {
    tft.fillTriangle(218, 4, 218, 14, 227, 9, SPOTIFY_GREEN);
  } else {
    tft.fillRect(217, 4, 3, 10, MUTED_TEXT);
    tft.fillRect(224, 4, 3, 10, MUTED_TEXT);
  }
}

void drawTrackBase() {
  lastProgressFilled = -1;
  lastProgressFraction = 255;
  lastProgressSecond = UINT32_MAX;

  tft.fillScreen(APP_BACKGROUND);
  tft.fillRoundRect(4, 19, 232, 83, 8, TRACK_CARD);
  tft.drawRoundRect(4, 19, 232, 83, 8, CARD_BORDER);

  tft.setTextSize(1);
  tft.setTextColor(SPOTIFY_GREEN);
  tft.setCursor(8, 6);
  tft.print(F("SPOTIFY"));
  tft.setTextColor(MUTED_TEXT);
  tft.setCursor(58, 6);
  tft.print(F("NOW PLAYING"));
  drawPlaybackState();

  tft.drawRoundRect(
    ART_FRAME_X,
    ART_FRAME_Y,
    ART_FRAME_SIZE,
    ART_FRAME_SIZE,
    5,
    CARD_BORDER
  );
  drawAlbumPlaceholder();

  char title[96];
  char artist[80];
  char album[80];
  copyUtf8Text(title, sizeof(title), currentTrack.title.c_str(), currentTrack.title.length());
  copyUtf8Text(artist, sizeof(artist), currentTrack.artist.c_str(), currentTrack.artist.length());
  copyUtf8Text(album, sizeof(album), currentTrack.album.c_str(), currentTrack.album.length());

  drawUtf8FittedCenteredLine(title, 96, 45, 136, ST77XX_WHITE, true);
  drawUtf8FittedCenteredLine(artist, 96, 69, 136, MUTED_TEXT);
  drawUtf8FittedCenteredLine(album, 96, 90, 136, DIM_TEXT);

  lastDrawnLyric = -999;
}

uint32_t estimatedPlayheadMs() {
  if (!hasCurrentTrack) return 0;

  uint32_t playhead = currentTrack.progressMs;
  if (currentTrack.isPlaying) {
    playhead += millis() - currentTrack.snapshotAtMs;
  }

  if (playhead > currentTrack.durationMs) playhead = currentTrack.durationMs;
  return playhead;
}

void matrixWriteAll(uint8_t address, uint8_t value) {
  digitalWrite(MATRIX_CS, LOW);
  for (uint8_t device = 0; device < MATRIX_DEVICE_COUNT; device++) {
    shiftOut(MATRIX_DIN, MATRIX_CLK, MSBFIRST, address);
    shiftOut(MATRIX_DIN, MATRIX_CLK, MSBFIRST, value);
  }
  digitalWrite(MATRIX_CS, HIGH);
}

void flushMusicMatrix() {
  for (uint8_t row = 0; row < 8; row++) {
    digitalWrite(MATRIX_CS, LOW);
    // The first bytes shifted travel to the panel furthest from DIN. Sending
    // device 3 first leaves device 0 in the panel nearest the IN connector.
    for (int8_t device = MATRIX_DEVICE_COUNT - 1; device >= 0; device--) {
      shiftOut(MATRIX_DIN, MATRIX_CLK, MSBFIRST, row + 1);
      shiftOut(MATRIX_DIN, MATRIX_CLK, MSBFIRST, matrixRows[device][row]);
    }
    digitalWrite(MATRIX_CS, HIGH);
  }
}

void beginMusicMatrix() {
  pinMode(MATRIX_DIN, OUTPUT);
  pinMode(MATRIX_CLK, OUTPUT);
  pinMode(MATRIX_CS, OUTPUT);
  digitalWrite(MATRIX_DIN, LOW);
  digitalWrite(MATRIX_CLK, LOW);
  digitalWrite(MATRIX_CS, HIGH);

  matrixWriteAll(0x0C, 0x00);  // Shutdown while configuring.
  matrixWriteAll(0x0F, 0x00);  // Display test off.
  matrixWriteAll(0x09, 0x00);  // No BCD decoding.
  matrixWriteAll(0x0B, 0x07);  // Scan all eight rows.
  matrixWriteAll(0x0A, MATRIX_INTENSITY);
  memset(matrixRows, 0, sizeof(matrixRows));
  flushMusicMatrix();
}

void clearMusicMatrix() {
  memset(matrixRows, 0, sizeof(matrixRows));
  memset(matrixBarHeight, 0, sizeof(matrixBarHeight));
  memset(matrixTargetHeight, 0, sizeof(matrixTargetHeight));
  flushMusicMatrix();
  matrixWriteAll(0x0C, 0x00);  // True hardware shutdown: no LEDs when idle.
  matrixIsLit = false;
}

void setMusicMatrixPixel(uint8_t x, uint8_t yFromBottom) {
  if (x >= 8 || yFromBottom >= 32) return;

  // The photographed chain has DIN on the bottom panel. Device 0 is therefore
  // the bottom 8 rows, device 3 the top 8 rows.
  uint8_t logicalDevice = yFromBottom / 8;
  uint8_t device = MATRIX_REVERSE_STACK
    ? MATRIX_DEVICE_COUNT - 1 - logicalDevice
    : logicalDevice;
  uint8_t rowFromBottom = yFromBottom % 8;
  uint8_t registerRow = MATRIX_ROW_ZERO_IS_TOP
    ? 7 - rowFromBottom
    : rowFromBottom;
  uint8_t columnBit = MATRIX_MIRROR_HORIZONTAL ? x : 7 - x;
  matrixRows[device][registerRow] |= (uint8_t)(1U << columnBit);
}

uint32_t matrixTrackSeed() {
  uint32_t seed = 2166136261UL;
  for (unsigned int i = 0; i < currentTrack.id.length(); i++) {
    seed ^= (uint8_t)currentTrack.id[i];
    seed *= 16777619UL;
  }
  return seed;
}

void chooseMusicMatrixTargets(uint32_t playhead) {
  uint32_t trackSeed = matrixTrackSeed();
  uint16_t simulatedBpm = 90 + (trackSeed % 61);  // 90..150 BPM.
  uint32_t beatLength = 60000UL / simulatedBpm;
  uint32_t beatPhase = playhead % beatLength;
  uint8_t pulse = beatPhase < 110 ? (uint8_t)(8 - beatPhase * 8 / 110) : 0;

  uint32_t seed = trackSeed ^ (playhead / MATRIX_TARGET_MS) * 2654435761UL;
  for (uint8_t column = 0; column < 8; column++) {
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;

    uint8_t target = 5 + (seed % 22) + pulse;
    // Slightly taller centre columns make the animation read as an equalizer.
    if (column >= 2 && column <= 5) target += 2;
    matrixTargetHeight[column] = target > 32 ? 32 : target;
  }
}

void updateMusicMatrix() {
  bool reachedTrackEnd = hasCurrentTrack &&
                         currentTrack.durationMs > 0 &&
                         estimatedPlayheadMs() >= currentTrack.durationMs;
  if (!hasCurrentTrack || !currentTrack.isPlaying || reachedTrackEnd) {
    if (matrixIsLit) clearMusicMatrix();
    return;
  }

  if (millis() - lastMatrixUpdateAtMs < MATRIX_UPDATE_MS) return;
  lastMatrixUpdateAtMs = millis();

  uint32_t playhead = estimatedPlayheadMs();
  if (timeReached(nextMatrixTargetAtMs)) {
    chooseMusicMatrixTargets(playhead);
    nextMatrixTargetAtMs = millis() + MATRIX_TARGET_MS;
  }

  if (!matrixIsLit) {
    matrixWriteAll(0x0C, 0x01);  // Leave shutdown only while music is playing.
    matrixIsLit = true;
  }

  memset(matrixRows, 0, sizeof(matrixRows));
  for (uint8_t column = 0; column < 8; column++) {
    int16_t difference =
      (int16_t)matrixTargetHeight[column] - matrixBarHeight[column];
    if (difference > 0) {
      matrixBarHeight[column] += difference > 4 ? 4 : difference;
    } else if (difference < 0) {
      uint8_t fall = -difference > 3 ? 3 : (uint8_t)(-difference);
      matrixBarHeight[column] -= fall;
    }

    for (uint8_t y = 0; y < matrixBarHeight[column]; y++) {
      setMusicMatrixPixel(column, y);
    }
  }

  flushMusicMatrix();
}

uint16_t blendRgb565(uint16_t from, uint16_t to, uint8_t amount) {
  uint16_t inverse = 255 - amount;
  uint8_t fromR = (from >> 11) & 0x1F;
  uint8_t fromG = (from >> 5) & 0x3F;
  uint8_t fromB = from & 0x1F;
  uint8_t toR = (to >> 11) & 0x1F;
  uint8_t toG = (to >> 5) & 0x3F;
  uint8_t toB = to & 0x1F;

  uint8_t red = (fromR * inverse + toR * amount + 127) / 255;
  uint8_t green = (fromG * inverse + toG * amount + 127) / 255;
  uint8_t blue = (fromB * inverse + toB * amount + 127) / 255;
  return (red << 11) | (green << 5) | blue;
}

void drawProgress() {
  if (!hasCurrentTrack) return;

  uint32_t playhead = estimatedPlayheadMs();
  uint16_t filled = 0;
  uint8_t fraction = 0;
  if (currentTrack.durationMs > 0) {
    uint64_t progress256 =
      (uint64_t)PROGRESS_WIDTH * 256ULL * playhead / currentTrack.durationMs;
    filled = progress256 >> 8;
    fraction = progress256 & 0xFF;
    if (filled >= PROGRESS_WIDTH) {
      filled = PROGRESS_WIDTH;
      fraction = 0;
    }
  }

  bool resetBar = lastProgressFilled < 0 || filled < lastProgressFilled;
  bool progressChanged = resetBar || filled != lastProgressFilled ||
                         fraction != lastProgressFraction;
  if (progressChanged && resetBar) {
    tft.fillRoundRect(
      PROGRESS_X,
      PROGRESS_Y,
      PROGRESS_WIDTH,
      PROGRESS_HEIGHT,
      2,
      DIM_TEXT
    );
  }
  if (progressChanged && filled > 0 &&
      (resetBar || filled != lastProgressFilled)) {
    tft.fillRoundRect(
      PROGRESS_X,
      PROGRESS_Y,
      filled,
      PROGRESS_HEIGHT,
      2,
      SPOTIFY_GREEN
    );
  }
  if (progressChanged && filled < PROGRESS_WIDTH) {
    uint16_t partialColour = blendRgb565(DIM_TEXT, SPOTIFY_GREEN, fraction);
    tft.drawFastVLine(
      PROGRESS_X + filled,
      PROGRESS_Y,
      PROGRESS_HEIGHT,
      partialColour
    );
  }
  lastProgressFilled = filled;
  lastProgressFraction = fraction;

  uint32_t progressSecond = playhead / 1000UL;
  if (progressSecond == lastProgressSecond) return;
  lastProgressSecond = progressSecond;

  char currentText[12];
  char durationText[12];
  formatTime(playhead, currentText, sizeof(currentText));
  formatTime(currentTrack.durationMs, durationText, sizeof(durationText));

  tft.setTextSize(1);
  tft.setTextColor(MUTED_TEXT);
  tft.fillRect(8, 113, 48, 9, APP_BACKGROUND);
  tft.setCursor(8, 114);
  tft.print(currentText);

  int16_t durationX = 232 - (int16_t)strlen(durationText) * 6;
  tft.fillRect(184, 113, 48, 9, APP_BACKGROUND);
  tft.setCursor(durationX, 114);
  tft.print(durationText);
}

int activeLyricIndex(uint32_t playhead) {
  int active = -1;
  for (size_t i = 0; i < lyricLineCount; i++) {
    if (lyricLines[i].atMs > playhead) break;
    active = (int)i;
  }
  return active;
}

uint32_t readUtf8CodePoint(const char*& cursor) {
  uint8_t first = (uint8_t)*cursor++;
  if (first < 0x80) return first;

  uint8_t continuationCount = 0;
  uint32_t codePoint = 0;
  if ((first & 0xE0) == 0xC0) {
    continuationCount = 1;
    codePoint = first & 0x1F;
  } else if ((first & 0xF0) == 0xE0) {
    continuationCount = 2;
    codePoint = first & 0x0F;
  } else if ((first & 0xF8) == 0xF0) {
    continuationCount = 3;
    codePoint = first & 0x07;
  } else {
    return 0xFFFD;
  }

  while (continuationCount-- > 0 && *cursor != '\0') {
    uint8_t next = (uint8_t)*cursor;
    if ((next & 0xC0) != 0x80) return 0xFFFD;
    cursor++;
    codePoint = (codePoint << 6) | (next & 0x3F);
  }
  return codePoint;
}

bool containsNonAscii(const char* text) {
  while (*text != '\0') {
    if ((uint8_t)*text++ >= 0x80) return true;
  }
  return false;
}

bool isKoreanCodePoint(uint32_t codePoint) {
  return (codePoint >= 0x1100 && codePoint <= 0x11FF) ||
         (codePoint >= 0x3130 && codePoint <= 0x318F) ||
         (codePoint >= 0xAC00 && codePoint <= 0xD7AF);
}

bool isChineseCodePoint(uint32_t codePoint) {
  return (codePoint >= 0x3400 && codePoint <= 0x9FFF) ||
         (codePoint >= 0xF900 && codePoint <= 0xFAFF);
}

bool isThaiCodePoint(uint32_t codePoint) {
  return codePoint >= 0x0E00 && codePoint <= 0x0E7F;
}

bool fontContainsGlyph(const uint8_t* font, uint16_t codePoint) {
  unicodeText.setFont(font);
  return u8g2_IsGlyph(&unicodeText.u8g2, codePoint) != 0;
}

bool cjk16GlyphOffset(uint32_t codePoint, uint32_t& byteOffset) {
  for (uint8_t i = 0; i < CJK16_RANGE_COUNT; i++) {
    uint16_t first = pgm_read_word(&CJK16_RANGE_FIRST[i]);
    uint16_t last = pgm_read_word(&CJK16_RANGE_LAST[i]);
    if (codePoint < first || codePoint > last) continue;

    uint32_t rangeOffset = pgm_read_dword(&CJK16_RANGE_OFFSET[i]);
    byteOffset = (rangeOffset + codePoint - first) * CJK16_BYTES_PER_GLYPH;
    return true;
  }
  return false;
}

void drawCjk16Glyph(
  int16_t x,
  int16_t baselineY,
  uint32_t byteOffset,
  uint16_t colour,
  bool bold
) {
  // GNU Unifont's 16-pixel cells extend from 14 pixels above the baseline
  // to 2 pixels below it, matching the baseline convention used by U8g2.
  int16_t top = baselineY - 14;

  for (uint8_t row = 0; row < CJK16_GLYPH_HEIGHT; row++) {
    uint32_t rowOffset = byteOffset + row * 2UL;
    uint16_t pixels = ((uint16_t)pgm_read_byte(&CJK16_BITMAPS[rowOffset]) << 8) |
                      pgm_read_byte(&CJK16_BITMAPS[rowOffset + 1]);

    uint8_t column = 0;
    while (column < CJK16_GLYPH_WIDTH) {
      while (column < CJK16_GLYPH_WIDTH &&
             (pixels & (0x8000U >> column)) == 0) {
        column++;
      }
      uint8_t runStart = column;
      while (column < CJK16_GLYPH_WIDTH &&
             (pixels & (0x8000U >> column)) != 0) {
        column++;
      }
      if (column > runStart) {
        uint8_t runWidth = column - runStart;
        tft.drawFastHLine(x + runStart, top + row, runWidth, colour);
        if (bold) {
          tft.drawFastHLine(x + runStart + 1, top + row, runWidth, colour);
        }
      }
    }
  }
}

const uint8_t* fontForCodePoint(uint32_t codePoint) {
  if (isKoreanCodePoint(codePoint)) {
    return u8g2_font_unifont_t_korean2;
  }
  if (isThaiCodePoint(codePoint)) {
    return u8g2_font_etl16thai_t;
  }

  return u8g2_font_unifont_t_latin;
}

const uint8_t* resolveGlyphFont(uint32_t& codePoint) {
  const uint8_t* font = fontForCodePoint(codePoint);
  uint16_t glyph = codePoint <= 0xFFFF ? (uint16_t)codePoint : (uint16_t)'?';
  if (fontContainsGlyph(font, glyph)) return font;

  codePoint = '?';
  unicodeText.setFont(u8g2_font_unifont_t_latin);
  return u8g2_font_unifont_t_latin;
}

int16_t unicodeGlyphAdvance(uint32_t codePoint) {
  uint32_t byteOffset;
  if (cjk16GlyphOffset(codePoint, byteOffset)) return CJK16_GLYPH_WIDTH;

  const uint8_t* font = resolveGlyphFont(codePoint);
  unicodeText.setFont(font);
  int16_t width = u8g2_GetGlyphWidth(&unicodeText.u8g2, (uint16_t)codePoint);
  return width > 0 ? width : 0;
}

int16_t measureUtf8WithFallback(const char* text) {
  int16_t width = 0;
  const char* cursor = text;
  while (*cursor != '\0') {
    uint32_t codePoint = readUtf8CodePoint(cursor);
    width += unicodeGlyphAdvance(codePoint);
  }
  return width;
}

void removeLastUtf8Character(char* text) {
  size_t length = strlen(text);
  if (length == 0) return;
  length--;
  while (length > 0 && (((uint8_t)text[length] & 0xC0) == 0x80)) length--;
  text[length] = '\0';
}

void fitUtf8ToWidth(
  const char* source,
  char* destination,
  size_t destinationSize,
  int16_t maxWidth
) {
  if (destinationSize == 0) return;
  destination[0] = '\0';

  size_t out = 0;
  bool truncated = false;
  const char* cursor = source;
  while (*cursor != '\0') {
    const char* glyphStart = cursor;
    readUtf8CodePoint(cursor);
    size_t glyphBytes = (size_t)(cursor - glyphStart);
    if (out + glyphBytes >= destinationSize) {
      truncated = true;
      break;
    }

    memcpy(destination + out, glyphStart, glyphBytes);
    out += glyphBytes;
    destination[out] = '\0';
    if (measureUtf8WithFallback(destination) > maxWidth) {
      out -= glyphBytes;
      destination[out] = '\0';
      truncated = true;
      break;
    }
  }

  if (!truncated) return;

  const char* ellipsis = "...";
  int16_t ellipsisWidth = measureUtf8WithFallback(ellipsis);
  while (destination[0] != '\0' &&
         measureUtf8WithFallback(destination) + ellipsisWidth > maxWidth) {
    removeLastUtf8Character(destination);
  }
  if (strlen(destination) + 3 < destinationSize) strcat(destination, ellipsis);
}

void drawUtf8FittedCenteredLine(
  const char* text,
  int16_t boxX,
  int16_t baselineY,
  int16_t boxWidth,
  uint16_t colour,
  bool bold
) {
  if (text[0] == '\0') return;

  char fitted[128];
  fitUtf8ToWidth(text, fitted, sizeof(fitted), boxWidth - (bold ? 1 : 0));
  int16_t width = measureUtf8WithFallback(fitted);
  int16_t x = boxX + max(0, (boxWidth - width) / 2);

  const char* cursor = fitted;
  while (*cursor != '\0') {
    uint32_t codePoint = readUtf8CodePoint(cursor);
    uint32_t cjkByteOffset;
    if (cjk16GlyphOffset(codePoint, cjkByteOffset)) {
      drawCjk16Glyph(x, baselineY, cjkByteOffset, colour, bold);
      x += CJK16_GLYPH_WIDTH;
      continue;
    }

    const uint8_t* font = resolveGlyphFont(codePoint);
    unicodeText.setFont(font);
    unicodeText.setForegroundColor(colour);
    int16_t advance = u8g2_GetGlyphWidth(
      &unicodeText.u8g2,
      (uint16_t)codePoint
    );
    unicodeText.drawGlyph(x, baselineY, (uint16_t)codePoint);
    if (bold) unicodeText.drawGlyph(x + 1, baselineY, (uint16_t)codePoint);
    if (advance > 0) x += advance;
  }
}

void drawLyrics(bool force = false) {
  int active = activeLyricIndex(estimatedPlayheadMs());
  if (!force && active == lastDrawnLyric) return;
  lastDrawnLyric = active;

  tft.fillRoundRect(
    LYRICS_PANEL_X,
    LYRICS_PANEL_Y,
    LYRICS_PANEL_WIDTH,
    LYRICS_PANEL_HEIGHT,
    8,
    LYRICS_CARD
  );
  tft.drawRoundRect(
    LYRICS_PANEL_X,
    LYRICS_PANEL_Y,
    LYRICS_PANEL_WIDTH,
    LYRICS_PANEL_HEIGHT,
    8,
    CARD_BORDER
  );
  tft.fillRoundRect(10, 131, 3, 12, 1, SPOTIFY_GREEN);
  tft.setTextSize(1);
  tft.setTextColor(SPOTIFY_GREEN);
  tft.setCursor(18, 133);
  tft.print(F("LIVE LYRICS"));

  if (lyricLineCount == 0) {
    char status[128];
    stringToDisplayText(lyricStatus, status, sizeof(status));
    drawWrappedCentered(status, 18, 169, 204, 1, MUTED_TEXT, 4);
    return;
  }

  const char* previous = (active > 0) ? lyricLines[active - 1].text : "";
  const char* current = (active >= 0) ? lyricLines[active].text : "...";
  const char* next = "";
  if (active + 1 < (int)lyricLineCount) next = lyricLines[active + 1].text;

  drawUtf8FittedCenteredLine(previous, 14, 160, 212, DIM_TEXT);
  tft.fillRoundRect(9, 171, 3, 23, 1, SPOTIFY_GREEN);
  drawUtf8FittedCenteredLine(current, 14, 190, 212, ST77XX_WHITE, true);
  drawUtf8FittedCenteredLine(next, 14, 220, 212, MUTED_TEXT);
}

// =============================================================================
// JPEG album-art rendering
// =============================================================================

bool splitHttpsUrl(const String& url, String& host, String& path) {
  const String prefix = "https://";
  if (!url.startsWith(prefix)) return false;

  int slash = url.indexOf('/', prefix.length());
  if (slash < 0) {
    host = url.substring(prefix.length());
    path = "/";
  } else {
    host = url.substring(prefix.length(), slash);
    path = url.substring(slash);
  }

  return host.length() > 0;
}

bool renderAlbumJpeg(uint8_t* jpegData, size_t jpegLength) {
  if (JpegDec.decodeArray(jpegData, jpegLength) == 0) return false;

  int16_t imageWidth = JpegDec.width;
  int16_t imageHeight = JpegDec.height;

  // Spotify normally supplies 64x64 as the smallest image. Reject unexpectedly
  // large images rather than drawing into the player text.
  if (imageWidth > ART_INNER_SIZE || imageHeight > ART_INNER_SIZE) {
    JpegDec.abort();
    return false;
  }

  int16_t originX = ART_FRAME_X + 2 + (ART_INNER_SIZE - imageWidth) / 2;
  int16_t originY = ART_FRAME_Y + 2 + (ART_INNER_SIZE - imageHeight) / 2;

  tft.fillRect(
    ART_FRAME_X + 2,
    ART_FRAME_Y + 2,
    ART_INNER_SIZE,
    ART_INNER_SIZE,
    TRACK_CARD
  );

  while (JpegDec.read()) {
    uint16_t* pixels = JpegDec.pImage;
    int16_t mcuWidth = JpegDec.MCUWidth;
    int16_t mcuHeight = JpegDec.MCUHeight;
    int16_t x = originX + JpegDec.MCUx * mcuWidth;
    int16_t y = originY + JpegDec.MCUy * mcuHeight;
    int16_t remainingWidth =
      imageWidth - (int16_t)(JpegDec.MCUx * mcuWidth);
    int16_t remainingHeight =
      imageHeight - (int16_t)(JpegDec.MCUy * mcuHeight);
    int16_t drawWidth = mcuWidth < remainingWidth ? mcuWidth : remainingWidth;
    int16_t drawHeight = mcuHeight < remainingHeight ? mcuHeight : remainingHeight;

    for (int16_t row = 0; row < drawHeight; row++) {
      tft.drawRGBBitmap(x, y + row, pixels + row * mcuWidth, drawWidth, 1);
    }
  }

  return true;
}

bool fetchAndDrawAlbumArt(const String& initialUrl) {
  if (initialUrl.length() == 0) return false;
  String url = initialUrl;

  for (uint8_t redirect = 0; redirect < 2; redirect++) {
    String host;
    String path;
    if (!splitHttpsUrl(url, host, path)) return false;
    if (!openHttps(host.c_str())) return false;

    secureClient.print(F("GET "));
    secureClient.print(path);
    secureClient.println(F(" HTTP/1.1"));
    secureClient.print(F("Host: "));
    secureClient.println(host);
    secureClient.println(F("User-Agent: MakerLabSpotifyTFT/1.0"));
    secureClient.println(F("Accept: image/jpeg"));
    secureClient.println(F("Accept-Encoding: identity"));
    secureClient.println(F("Connection: close"));
    secureClient.println();

    HttpResponse response;
    if (!readHttpResponseHeaders(secureClient, response)) {
      secureClient.stop();
      return false;
    }

    if ((response.status == 301 || response.status == 302 ||
         response.status == 307 || response.status == 308) &&
        response.location.length() > 0) {
      url = response.location;
      secureClient.stop();
      continue;
    }

    if (response.status != 200 ||
        response.contentLength > (long)MAX_ALBUM_JPEG_BYTES) {
      secureClient.stop();
      return false;
    }

    // Use the JPEG's real size when the server provides it. Allocating the
    // full 8 KB every time can fail after Wi-Fi and JSON have used the heap.
    size_t jpegCapacity = MAX_ALBUM_JPEG_BYTES;
    if (response.contentLength > 0) {
      jpegCapacity = (size_t)response.contentLength;
    }

    uint8_t* jpegData = (uint8_t*)malloc(jpegCapacity);
    if (jpegData == nullptr) {
      Serial.print(F("Not enough RAM for album art (bytes requested: "));
      Serial.print(jpegCapacity);
      Serial.println(F(")"));
      secureClient.stop();
      return false;
    }

    HttpBodyStream body(secureClient, response.contentLength, response.chunked);
    size_t length = 0;
    bool overflow = false;
    while (true) {
      int value = body.read();
      if (value < 0) break;
      if (length < jpegCapacity) {
        jpegData[length++] = (uint8_t)value;
      } else {
        overflow = true;
        break;
      }
    }

    secureClient.stop();
    bool rendered = false;
    if (!overflow && length > 4) rendered = renderAlbumJpeg(jpegData, length);
    free(jpegData);
    return rendered;
  }

  return false;
}

// =============================================================================
// Spotify authentication and polling
// =============================================================================

bool refreshSpotifyAccessToken() {
  if (WiFi.status() != WL_CONNECTED) return false;
  if (!openHttps("accounts.spotify.com")) {
    lyricStatus = "Cannot reach Spotify login";
    return false;
  }

  String body = "grant_type=refresh_token&refresh_token=" +
                urlEncode(SPOTIFY_REFRESH_TOKEN);
  String credentials = String(SPOTIFY_CLIENT_ID) + ":" + SPOTIFY_CLIENT_SECRET;
  String authorization = base64Encode(credentials);

  secureClient.println(F("POST /api/token HTTP/1.1"));
  secureClient.println(F("Host: accounts.spotify.com"));
  secureClient.print(F("Authorization: Basic "));
  secureClient.println(authorization);
  secureClient.println(F("Content-Type: application/x-www-form-urlencoded"));
  secureClient.print(F("Content-Length: "));
  secureClient.println(body.length());
  secureClient.println(F("Accept: application/json"));
  secureClient.println(F("Accept-Encoding: identity"));
  secureClient.println(F("Connection: close"));
  secureClient.println();
  secureClient.print(body);

  HttpResponse response;
  if (!readHttpResponseHeaders(secureClient, response)) {
    secureClient.stop();
    return false;
  }

  HttpBodyStream responseBody(
    secureClient,
    response.contentLength,
    response.chunked
  );

  JsonDocument filter;
  filter["access_token"] = true;
  filter["expires_in"] = true;
  filter["error"] = true;
  filter["error_description"] = true;

  JsonDocument document;
  DeserializationError jsonError = deserializeJson(
    document,
    responseBody,
    DeserializationOption::Filter(filter)
  );
  secureClient.stop();

  if (response.status != 200 || jsonError) {
    const char* apiError = document["error"] | "unknown_error";
    const char* apiDescription = document["error_description"] | "";
    Serial.print(F("Spotify token error, HTTP "));
    Serial.print(response.status);
    Serial.print(F(": "));
    Serial.println(apiError);
    if (apiDescription[0] != '\0') {
      Serial.print(F("Spotify says: "));
      Serial.println(apiDescription);
    }

    lyricStatus = "Spotify authentication failed";
    nextSpotifyPollAtMs = millis() + AUTH_ERROR_RETRY_MS;

    if (!spotifyAuthErrorShown) {
      if (strcmp(apiError, "invalid_grant") == 0) {
        drawStatusScreen(
          "INVALID TOKEN",
          "Run Get-Spotify-Refresh-Token.cmd, then upload again"
        );
      } else if (strcmp(apiError, "invalid_client") == 0) {
        drawStatusScreen(
          "APP LOGIN ERROR",
          "Check the Spotify client ID and client secret"
        );
      } else {
        drawStatusScreen(
          "SPOTIFY LOGIN ERROR",
          "Check Serial Monitor for the exact error"
        );
      }
      spotifyAuthErrorShown = true;
    }
    return false;
  }

  const char* token = document["access_token"] | "";
  uint32_t expiresIn = document["expires_in"] | 3600;
  if (token[0] == '\0') return false;

  spotifyAccessToken = token;
  spotifyAuthErrorShown = false;
  uint32_t refreshInSeconds = expiresIn > 90 ? expiresIn - 60 : expiresIn / 2;
  tokenRefreshAtMs = millis() + refreshInSeconds * 1000UL;
  Serial.println(F("Spotify access token refreshed"));
  return true;
}

void clearTrackAndShowIdle(const char* heading, const char* detail) {
  clearMusicMatrix();
  bool neededRedraw = hasCurrentTrack;
  hasCurrentTrack = false;
  currentTrack = TrackInfo();
  lyricLineCount = 0;
  if (neededRedraw || lastDrawnLyric != -998) {
    drawStatusScreen(heading, detail);
    lastDrawnLyric = -998;
  }
}

// =============================================================================
// LRCLIB lyrics
// =============================================================================

uint32_t parseLrcTimestamp(const char* start, const char* end) {
  const char* colon = (const char*)memchr(start, ':', end - start);
  if (colon == nullptr) return 0;

  uint32_t minutes = strtoul(start, nullptr, 10);
  uint32_t seconds = strtoul(colon + 1, nullptr, 10);
  uint32_t fractionMs = 0;

  const char* dot = (const char*)memchr(colon + 1, '.', end - (colon + 1));
  if (dot != nullptr && dot + 1 < end) {
    uint8_t digits = 0;
    for (const char* p = dot + 1; p < end && digits < 3; p++, digits++) {
      if (!isdigit((uint8_t)*p)) break;
      fractionMs = fractionMs * 10 + (*p - '0');
    }
    if (digits == 1) fractionMs *= 100;
    if (digits == 2) fractionMs *= 10;
  }

  return (minutes * 60UL + seconds) * 1000UL + fractionMs;
}

void storeLrcLine(const char* cursor, size_t length) {
  if (lyricLineCount >= MAX_LYRIC_LINES || length == 0 || *cursor != '[') {
    return;
  }

  const char* lineEnd = cursor + length;
  const char* closing = (const char*)memchr(cursor, ']', length);
  if (closing == nullptr) return;

  const char* textStart = closing + 1;
  while (textStart < lineEnd && (*textStart == ' ' || *textStart == '\r')) {
    textStart++;
  }

  const char* textEnd = lineEnd;
  while (textEnd > textStart &&
         (textEnd[-1] == ' ' || textEnd[-1] == '\r')) {
    textEnd--;
  }
  if (textEnd <= textStart) return;

  LyricLine& line = lyricLines[lyricLineCount++];
  line.atMs = parseLrcTimestamp(cursor + 1, closing);
  copyUtf8Text(
    line.text,
    sizeof(line.text),
    textStart,
    textEnd - textStart
  );
  if (line.text[0] == '\0') lyricLineCount--;
}

void parseSyncedLyrics(const char* lyrics) {
  lyricLineCount = 0;
  if (lyrics == nullptr) return;

  const char* cursor = lyrics;
  while (*cursor != '\0' && lyricLineCount < MAX_LYRIC_LINES) {
    const char* lineEnd = strchr(cursor, '\n');
    if (lineEnd == nullptr) lineEnd = cursor + strlen(cursor);

    storeLrcLine(cursor, lineEnd - cursor);

    cursor = *lineEnd == '\0' ? lineEnd : lineEnd + 1;
  }
}

int8_t jsonHexValue(int value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

void appendLrcByte(char* line, size_t capacity, size_t& length, uint8_t value) {
  if (length + 1 < capacity) line[length++] = (char)value;
}

void appendLrcCodePoint(
  char* line,
  size_t capacity,
  size_t& length,
  uint32_t codePoint
) {
  if (codePoint <= 0x7F) {
    appendLrcByte(line, capacity, length, codePoint);
  } else if (codePoint <= 0x7FF) {
    appendLrcByte(line, capacity, length, 0xC0 | (codePoint >> 6));
    appendLrcByte(line, capacity, length, 0x80 | (codePoint & 0x3F));
  } else if (codePoint <= 0xFFFF &&
             !(codePoint >= 0xD800 && codePoint <= 0xDFFF)) {
    appendLrcByte(line, capacity, length, 0xE0 | (codePoint >> 12));
    appendLrcByte(line, capacity, length, 0x80 | ((codePoint >> 6) & 0x3F));
    appendLrcByte(line, capacity, length, 0x80 | (codePoint & 0x3F));
  }
}

void finishStreamedLrcLine(char* line, size_t& length) {
  line[length] = '\0';
  storeLrcLine(line, length);
  length = 0;
}

bool extractSyncedLyricsFromJson(
  Stream& body,
  bool& instrumental,
  bool& foundSyncedField
) {
  static const char syncPattern[] = "\"syncedLyrics\":";
  static const char instrumentalPattern[] = "\"instrumental\":true";
  size_t syncMatch = 0;
  size_t instrumentalMatch = 0;
  instrumental = false;
  foundSyncedField = false;

  while (true) {
    int value = body.read();
    if (value < 0) return false;

    if (value == syncPattern[syncMatch]) syncMatch++;
    else syncMatch = value == syncPattern[0] ? 1 : 0;

    if (value == instrumentalPattern[instrumentalMatch]) instrumentalMatch++;
    else instrumentalMatch = value == instrumentalPattern[0] ? 1 : 0;
    if (instrumentalMatch == sizeof(instrumentalPattern) - 1) {
      instrumental = true;
      instrumentalMatch = 0;
    }

    if (syncMatch == sizeof(syncPattern) - 1) break;
  }

  foundSyncedField = true;
  int value;
  do {
    value = body.read();
  } while (value >= 0 && isspace((uint8_t)value));

  if (value < 0) return false;
  if (value == 'n') return true;  // JSON null: no synchronized lyrics.
  if (value != '"') return false;

  char streamedLine[MAX_LYRIC_CHARS + 32];
  size_t streamedLength = 0;
  while (true) {
    value = body.read();
    if (value < 0) return false;
    if (value == '"') {
      if (streamedLength > 0) finishStreamedLrcLine(streamedLine, streamedLength);
      return true;
    }

    if (value != '\\') {
      if (value == '\n') finishStreamedLrcLine(streamedLine, streamedLength);
      else appendLrcByte(streamedLine, sizeof(streamedLine), streamedLength, value);
      continue;
    }

    int escaped = body.read();
    if (escaped < 0) return false;
    if (escaped == 'n') {
      finishStreamedLrcLine(streamedLine, streamedLength);
    } else if (escaped == 'r') {
      // Ignore CR; LF finishes the line.
    } else if (escaped == 't') {
      appendLrcByte(streamedLine, sizeof(streamedLine), streamedLength, ' ');
    } else if (escaped == 'u') {
      uint32_t codePoint = 0;
      for (uint8_t digit = 0; digit < 4; digit++) {
        int hexCharacter = body.read();
        int8_t hex = jsonHexValue(hexCharacter);
        if (hex < 0) return false;
        codePoint = (codePoint << 4) | hex;
      }
      appendLrcCodePoint(
        streamedLine,
        sizeof(streamedLine),
        streamedLength,
        codePoint
      );
    } else {
      appendLrcByte(streamedLine, sizeof(streamedLine), streamedLength, escaped);
    }
  }
}

bool fetchLyricsForCurrentTrack() {
  lyricLineCount = 0;
  lyricStatus = "Looking for synchronised lyrics...";
  drawLyrics(true);

  if (!hasCurrentTrack) return false;
  if (!openHttps("lrclib.net")) {
    lyricStatus = "Lyrics service is offline";
    drawLyrics(true);
    return false;
  }

  String path = "/api/get?track_name=" + urlEncode(currentTrack.title) +
                "&artist_name=" + urlEncode(currentTrack.artist) +
                "&album_name=" + urlEncode(currentTrack.album) +
                "&duration=" + String(currentTrack.durationMs / 1000UL);

  secureClient.print(F("GET "));
  secureClient.print(path);
  secureClient.println(F(" HTTP/1.1"));
  secureClient.println(F("Host: lrclib.net"));
  secureClient.print(F("User-Agent: "));
  secureClient.println(LRCLIB_USER_AGENT);
  secureClient.println(F("Accept: application/json"));
  secureClient.println(F("Accept-Encoding: identity"));
  secureClient.println(F("Connection: close"));
  secureClient.println();

  HttpResponse response;
  if (!readHttpResponseHeaders(secureClient, response)) {
    secureClient.stop();
    lyricStatus = "Lyrics request timed out";
    drawLyrics(true);
    return false;
  }

  if (response.status == 404) {
    secureClient.stop();
    lyricStatus = "No lyrics found for this version";
    drawLyrics(true);
    return false;
  }

  if (response.status == 429) {
    secureClient.stop();
    lyricStatus = "Lyrics rate limit reached; try later";
    drawLyrics(true);
    return false;
  }

  if (response.status != 200) {
    secureClient.stop();
    lyricStatus = "Lyrics service returned an error";
    drawLyrics(true);
    return false;
  }

  HttpBodyStream body(secureClient, response.contentLength, response.chunked);
  bool instrumental = false;
  bool foundSyncedField = false;
  bool parsed = extractSyncedLyricsFromJson(
    body,
    instrumental,
    foundSyncedField
  );
  secureClient.stop();

  if (!parsed) {
    Serial.println(F("Lyrics stream ended before synchronized lyrics were read"));
    lyricStatus = "Lyrics response was incomplete";
    drawLyrics(true);
    return false;
  }

  if (instrumental) {
    lyricStatus = "Instrumental track";
    drawLyrics(true);
    return true;
  }

  lyricStatus = lyricLineCount > 0
    ? "Lyrics ready"
    : foundSyncedField
      ? "Only unsynchronised lyrics are available"
      : "Synchronized lyrics field was missing";
  drawLyrics(true);
  return lyricLineCount > 0;
}

void animateTrackTransition() {
  // A dark left-to-right curtain replaces the old player before the new card
  // is drawn. It avoids the bright full-screen clear that looks like a blink.
  const int16_t stripWidth = 12;
  for (int16_t x = 0; x < SCREEN_WIDTH; x += stripWidth) {
    int16_t remaining = SCREEN_WIDTH - x;
    int16_t width = stripWidth < remaining ? stripWidth : remaining;
    tft.fillRect(x, 0, width, SCREEN_HEIGHT, APP_BACKGROUND);
    delay(3);
  }
}

void handleNewTrack() {
  animateTrackTransition();
  lyricLineCount = 0;
  lyricStatus = "Loading track...";

  drawTrackBase();
  drawProgress();
  drawLyrics(true);

  // Parse lyrics before JPEG work so ArduinoJson gets an unfragmented heap.
  fetchLyricsForCurrentTrack();

  if (!fetchAndDrawAlbumArt(currentTrack.artUrl)) {
    Serial.println(F("Album art unavailable; using placeholder"));
  }
}

bool pollSpotify() {
  if (WiFi.status() != WL_CONNECTED) return false;

  if (spotifyAccessToken.length() == 0 || timeReached(tokenRefreshAtMs)) {
    if (!refreshSpotifyAccessToken()) return false;
  }

  if (!openHttps("api.spotify.com")) return false;

  secureClient.println(F("GET /v1/me/player/currently-playing HTTP/1.1"));
  secureClient.println(F("Host: api.spotify.com"));
  secureClient.print(F("Authorization: Bearer "));
  secureClient.println(spotifyAccessToken);
  secureClient.println(F("Accept: application/json"));
  secureClient.println(F("Accept-Encoding: identity"));
  secureClient.println(F("Connection: close"));
  secureClient.println();

  HttpResponse response;
  if (!readHttpResponseHeaders(secureClient, response)) {
    secureClient.stop();
    return false;
  }

  if (response.status == 204) {
    secureClient.stop();
    clearTrackAndShowIdle("NOTHING PLAYING", "Start a song in Spotify");
    return true;
  }

  if (response.status == 401) {
    secureClient.stop();
    spotifyAccessToken = "";
    tokenRefreshAtMs = 0;
    return false;
  }

  if (response.status == 429) {
    secureClient.stop();
    uint32_t waitSeconds = max(1, response.retryAfterSeconds);
    nextSpotifyPollAtMs = millis() + waitSeconds * 1000UL;
    Serial.println(F("Spotify rate limit; waiting"));
    return false;
  }

  if (response.status != 200) {
    secureClient.stop();
    Serial.print(F("Spotify HTTP error: "));
    Serial.println(response.status);
    return false;
  }

  String oldTrackId = currentTrack.id;
  bool previouslyHadTrack = hasCurrentTrack;

  {
    HttpBodyStream body(secureClient, response.contentLength, response.chunked);

    JsonDocument filter;
    filter["progress_ms"] = true;
    filter["is_playing"] = true;
    filter["item"]["id"] = true;
    filter["item"]["name"] = true;
    filter["item"]["duration_ms"] = true;
    filter["item"]["artists"][0]["name"] = true;
    filter["item"]["album"]["name"] = true;
    filter["item"]["album"]["images"][0]["url"] = true;
    filter["item"]["album"]["images"][0]["width"] = true;

    JsonDocument document;
    DeserializationError error = deserializeJson(
      document,
      body,
      DeserializationOption::Filter(filter)
    );

    if (error) {
      secureClient.stop();
      Serial.print(F("Spotify JSON error: "));
      Serial.println(error.c_str());
      return false;
    }

    if (document["item"].isNull() || document["item"]["id"].isNull()) {
      secureClient.stop();
      clearTrackAndShowIdle("NOTHING PLAYING", "Start a music track in Spotify");
      return true;
    }

    currentTrack.id = document["item"]["id"] | "";
    currentTrack.title = document["item"]["name"] | "Unknown title";
    currentTrack.artist = document["item"]["artists"][0]["name"] | "Unknown artist";
    currentTrack.album = document["item"]["album"]["name"] | "Unknown album";
    currentTrack.durationMs = document["item"]["duration_ms"] | 0UL;
    currentTrack.progressMs = document["progress_ms"] | 0UL;
    currentTrack.snapshotAtMs = millis();
    currentTrack.isPlaying = document["is_playing"] | false;

    currentTrack.artUrl = "";
    int smallestWidth = 32767;
    for (JsonObject image :
         document["item"]["album"]["images"].as<JsonArray>()) {
      int width = image["width"] | 0;
      const char* url = image["url"] | "";
      if (url[0] != '\0' && width > 0 && width < smallestWidth) {
        smallestWidth = width;
        currentTrack.artUrl = url;
      }
    }
  }

  secureClient.stop();
  hasCurrentTrack = true;

  bool trackChanged = !previouslyHadTrack || currentTrack.id != oldTrackId;
  if (trackChanged) {
    Serial.print(F("Now playing: "));
    Serial.print(currentTrack.title);
    Serial.print(F(" - "));
    Serial.println(currentTrack.artist);
    handleNewTrack();
  } else {
    drawPlaybackState();
  }

  return true;
}

// =============================================================================
// Wi-Fi, setup and main loop
// =============================================================================

bool connectWiFi(uint32_t waitMs) {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.print(F("Connecting to Wi-Fi: "));
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < waitMs) {
    delay(250);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("Wi-Fi connected; IP: "));
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println(F("Wi-Fi connection failed"));
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(300);

  // This keeps the standalone sketch compatible with Spotify, LRCLIB and the
  // artwork CDN, which use different certificate chains. For a production
  // device, replace this with an up-to-date CA certificate bundle.
  secureClient.setInsecure();

  beginMusicMatrix();
  clearMusicMatrix();

  pinMode(TFT_RST, OUTPUT);
  digitalWrite(TFT_RST, HIGH);
  delay(20);
  digitalWrite(TFT_RST, LOW);
  delay(20);
  digitalWrite(TFT_RST, HIGH);
  delay(120);

  tft.init(SCREEN_WIDTH, SCREEN_HEIGHT);
  tft.setRotation(TFT_ROTATION);
  tft.invertDisplay(TFT_INVERT);
  tft.setTextWrap(false);
  unicodeText.begin(tft);
  unicodeText.setFontMode(1);
  unicodeText.setFontDirection(0);

  drawStatusScreen("SPOTIFY TFT", "Starting ESP32-S3...");
  Serial.println(F("MakerLab Spotify TFT for ESP32-S3 starting"));

  if (!configurationIsReady()) {
    drawStatusScreen(
      "SETUP NEEDED",
      "Add Wi-Fi and Spotify values to arduino_secrets.h"
    );
    Serial.println(F("Configuration placeholders have not been replaced"));
    return;
  }

  drawStatusScreen("CONNECTING", "Joining Wi-Fi...");
  if (connectWiFi(20000)) {
    drawStatusScreen("CONNECTED", "Checking Spotify playback...");
    nextSpotifyPollAtMs = millis();
  } else {
    drawStatusScreen("WI-FI OFFLINE", "Will retry automatically");
    nextWiFiAttemptAtMs = millis() + WIFI_RETRY_MS;
  }
}

void loop() {
  if (!configurationIsReady()) {
    delay(100);
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    if (matrixIsLit) clearMusicMatrix();

    if (timeReached(nextWiFiAttemptAtMs)) {
      drawStatusScreen("WI-FI OFFLINE", "Trying to reconnect...");
      if (connectWiFi(10000)) {
        spotifyAccessToken = "";
        tokenRefreshAtMs = 0;
        nextSpotifyPollAtMs = millis();
        drawStatusScreen("CONNECTED", "Checking Spotify playback...");
      }
      nextWiFiAttemptAtMs = millis() + WIFI_RETRY_MS;
    }

    delay(20);
    return;
  }

  if (timeReached(nextSpotifyPollAtMs)) {
    nextSpotifyPollAtMs = millis() + SPOTIFY_POLL_MS;
    pollSpotify();
  }

  updateMusicMatrix();

  if (hasCurrentTrack &&
      millis() - lastProgressUpdateAtMs >= PROGRESS_UPDATE_MS) {
    lastProgressUpdateAtMs = millis();
    drawProgress();
  }

  if (hasCurrentTrack &&
      millis() - lastLyricCheckAtMs >= LYRIC_CHECK_MS) {
    lastLyricCheckAtMs = millis();
    drawLyrics();
  }

  delay(5);
}
