#include "EPD_2in9g.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <mbedtls/base64.h>
#include <LittleFS.h>
#include "frame_status.h"
#include "freshness.h"
#include "polling.h"

// USB-powered device: USB CDC remains available for provisioning and diagnostics.
// Credentials are provisioned over USB and stored in NVS, never in source or logs.
struct NetworkConfig {
  uint32_t magic;
  char ssid[33];
  char password[65];
  char frameUrl[241];
  uint32_t refreshSeconds;
};
static const uint32_t CONFIG_MAGIC = 0x41534C32;
static NetworkConfig config = {};
static uint8_t frame[9472], incoming[9472];
static bool haveFrame = false, linkAvailable = false, statusPending = false;
static bool observedFresh = false, observedLink = false, cacheReady = false;
static uint32_t freshUntilAt = 0, cachedServerHash = 0;
static bool freshnessKnown = false;
static bool scanRunning = false;
static uint32_t lastScanAt = 0;

bool dataFresh() {
  return haveFrame && matchdayInkFreshnessActive(freshnessKnown, freshUntilAt, millis());
}
static bool configured = false, displayed = false, refreshRequested = false;
static bool wasConnected = false, discardLine = false;
static uint32_t lastHash = 0, lastDrawAt = 0, nextFetchAt = 0, lastWifiAttempt = 0;
static uint32_t displayCount = 0;
static uint32_t receivedServerHash = 0, drawnServerHash = 0;
static bool redrawRequested = false;
static int lastHttp = 0;
static size_t lastBytes = 0;
static const char *lastError = "not_configured";
static String commandLine;

uint32_t checksum(const uint8_t *data, size_t size) {
  uint32_t value = 2166136261u;
  for (size_t i = 0; i < size; ++i) value = (value ^ data[i]) * 16777619u;
  return value;
}

void report(const char *event) {
  Serial.printf("{\"event\":\"%s\",\"configured\":%s,\"wifi_connected\":%s,"
                "\"wifi_status\":%d,\"ip\":\"%s\",\"http_status\":%d,"
                "\"frame_bytes\":%u,\"display_count\":%lu,\"last_error\":\"%s\","
                "\"refresh_seconds\":%lu,\"data_fresh\":%s,\"link_available\":%s,\"scan_in_progress\":%s,\"cache_ready\":%s,\"cached_frame\":%s,\"next_check_in\":%lu,\"received_frame_hash\":%lu,\"drawn_frame_hash\":%lu}\n",
                event, configured ? "true" : "false",
                WiFi.status() == WL_CONNECTED ? "true" : "false", (int)WiFi.status(),
                WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "",
                lastHttp, (unsigned)lastBytes, (unsigned long)displayCount, lastError,
                (unsigned long)config.refreshSeconds, dataFresh() ? "true" : "false",
                linkAvailable ? "true" : "false", scanRunning ? "true" : "false",
                cacheReady ? "true" : "false", cachedServerHash ? "true" : "false",
                (unsigned long)((int32_t)(nextFetchAt - millis()) > 0 ?
                  ((uint32_t)(nextFetchAt - millis()) + 999) / 1000 : 0),
                (unsigned long)receivedServerHash, (unsigned long)drawnServerHash);
}

bool decodeToken(const String &token, char *out, size_t capacity) {
  if (token == "-") { out[0] = 0; return true; }
  size_t length = 0;
  int result = mbedtls_base64_decode((unsigned char *)out, capacity - 1, &length,
                                   (const unsigned char *)token.c_str(), token.length());
  if (result || length >= capacity || memchr(out, 0, length)) return false;
  out[length] = 0;
  return true;
}

void startWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setMinSecurity(config.password[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN);
  WiFi.begin(config.ssid, config.password);
  lastWifiAttempt = millis();
  lastError = "connecting";
  report("wifi_connecting");
}

String jsonString(const String &value) {
  String out = "\"";
  const char *hex = "0123456789abcdef";
  for (unsigned int i = 0; i < value.length(); ++i) {
    uint8_t c = value[i];
    if (c == '"' || c == '\\') { out += '\\'; out += (char)c; }
    else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
    else out += (char)c;
  }
  return out + "\"";
}

void beginScan() {
  if (scanRunning) { report("wifi_scan_started"); return; }
  if (lastScanAt && millis() - lastScanAt < 15000) { report("wifi_scan_throttled"); return; }
  WiFi.mode(WIFI_STA);
  scanRunning = true;
  lastScanAt = millis();
  WiFi.scanNetworks(true, false);
  report("wifi_scan_started");
}

void pollScan() {
  if (!scanRunning) return;
  int count = WiFi.scanComplete();
  if (count == WIFI_SCAN_RUNNING) return;
  scanRunning = false;
  if (count < 0) { report("wifi_scan_failed"); return; }
  String used[12];
  int usedCount = 0;
  Serial.print("{\"event\":\"wifi_scan_done\",\"scan_in_progress\":false,\"networks\":[");
  // WiFi.scanNetworks returns networks sorted by signal strength.
  for (int i = 0; i < count && usedCount < 12; ++i) {
    String ssid = WiFi.SSID(i);
    bool duplicate = false;
    for (int j = 0; j < usedCount; ++j) if (used[j] == ssid) duplicate = true;
    if (!ssid.length() || duplicate) continue;
    if (usedCount) Serial.print(',');
    used[usedCount++] = ssid;
    Serial.printf("{\"ssid\":%s,\"rssi\":%d,\"secure\":%s}", jsonString(ssid).c_str(),
                  WiFi.RSSI(i), WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "false" : "true");
  }
  Serial.println("]}");
  WiFi.scanDelete();
}

void loadCachedFrame() {
  cacheReady = LittleFS.begin(true);
  if (!cacheReady) return;
  File file = LittleFS.open("/last-frame.bin", "r");
  if (!file || file.size() != sizeof(frame) + 8) return;
  uint32_t magic = 0, hash = 0;
  file.read((uint8_t *)&magic, 4); file.read((uint8_t *)&hash, 4);
  if (magic != CONFIG_MAGIC || file.read(frame, sizeof(frame)) != sizeof(frame)) return;
  if (checksum(frame, sizeof(frame)) != hash) return;
  haveFrame = true;
  cachedServerHash = hash;
  receivedServerHash = hash;
  freshUntilAt = 0; // After power loss, freshness must be verified again.
}

void saveCachedFrame(uint32_t serverHash) {
  if (!cacheReady || serverHash == cachedServerHash) return;
  File file = LittleFS.open("/frame.tmp", "w");
  if (!file) return;
  uint32_t magic = CONFIG_MAGIC;
  bool ok = file.write((uint8_t *)&magic, 4) == 4 &&
            file.write((uint8_t *)&serverHash, 4) == 4 &&
            file.write(frame, sizeof(frame)) == sizeof(frame);
  file.close();
  if (ok && LittleFS.rename("/frame.tmp", "/last-frame.bin")) cachedServerHash = serverHash;
}

void processCommand(const String &line) {
  if (line == "MATCHDAY_INK_REDRAW") {
    redrawRequested = true; refreshRequested = true;
    report("refresh_requested"); return;
  }
  if (line == "MATCHDAY_INK_SCAN") { beginScan(); return; }
  if (line == "MATCHDAY_INK_STATUS") { report("status"); return; }
  if (line == "MATCHDAY_INK_REFRESH") {
    refreshRequested = true;
    report("refresh_requested");
    return;
  }
  if (line.startsWith("MATCHDAY_INK_INTERVAL ")) {
    long seconds = line.substring(sizeof("MATCHDAY_INK_INTERVAL ") - 1).toInt();
    if (!configured || (seconds != 0 && (seconds < 180 || seconds > 86400))) {
      lastError = "invalid_interval"; report("config_error"); return;
    }
    NetworkConfig next = config;
    next.refreshSeconds = seconds;
    Preferences store;
    if (!store.begin("matchdayInk", false)) { lastError = "storage_error"; report("config_error"); return; }
    size_t saved = store.putBytes("network", &next, sizeof(next)); store.end();
    if (saved != sizeof(next)) { lastError = "storage_error"; report("config_error"); return; }
    config = next; memset(&next, 0, sizeof(next)); lastError = "";
    nextFetchAt = 0;
    report("interval_updated"); return;
  }
  if (!line.startsWith("MATCHDAY_INK_CONFIG ")) return;
  String tokens[4];
  int from = sizeof("MATCHDAY_INK_CONFIG ") - 1;
  for (int i = 0; i < 4; ++i) {
    int end = line.indexOf(' ', from);
    if (i < 3 && end < 0) { lastError = "invalid_config"; report("config_error"); return; }
    tokens[i] = end < 0 ? line.substring(from) : line.substring(from, end);
    from = end + 1;
  }
  NetworkConfig next = {};
  next.magic = CONFIG_MAGIC;
  next.refreshSeconds = tokens[3].toInt();
  if (!decodeToken(tokens[0], next.ssid, sizeof(next.ssid)) ||
      !decodeToken(tokens[1], next.password, sizeof(next.password)) ||
      !decodeToken(tokens[2], next.frameUrl, sizeof(next.frameUrl)) ||
      !next.ssid[0] || (strlen(next.password) > 0 && strlen(next.password) < 8) ||
      (next.refreshSeconds != 0 && (next.refreshSeconds < 180 || next.refreshSeconds > 86400)) ||
      !String(next.frameUrl).startsWith("http://") || String(next.frameUrl).indexOf('@') >= 0) {
    lastError = "invalid_config"; report("config_error"); return;
  }
  Preferences store;
  if (!store.begin("matchdayInk", false)) { lastError = "storage_error"; report("config_error"); return; }
  size_t saved = store.putBytes("network", &next, sizeof(next));
  store.end();
  if (saved != sizeof(next)) { lastError = "storage_error"; report("config_error"); return; }
  config = next;
  memset(&next, 0, sizeof(next));
  configured = true;
  lastError = "";
  report("configured");
  WiFi.disconnect(false, false);
  wasConnected = false;
  nextFetchAt = 0;
  startWifi();
}

void readCommands() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (!discardLine) processCommand(commandLine);
      // Never echo a provisioning line: it contains encoded credentials.
      commandLine = "";
      discardLine = false;
    } else if (c != '\r' && !discardLine) {
      if (commandLine.length() >= 1024) { commandLine = ""; discardLine = true; }
      else commandLine += c;
    }
  }
}

void presentFrame() {
  if (!haveFrame) return;
  bool connected = linkAvailable && WiFi.status() == WL_CONNECTED;
  bool fresh = dataFresh();
  observedFresh = fresh;
  observedLink = connected;
  matchdayInkStatusIcons(frame, connected, fresh);
  uint32_t hash = checksum(frame, sizeof(frame));
  if (displayed && hash == lastHash && !redrawRequested) { statusPending = false; report("unchanged"); return; }
  if (displayed && millis() - lastDrawAt < 180000) {
    statusPending = true;
    return;
  }
  statusPending = false;
  report("display_starting");
  DEV_Module_Init();
  EPD_2IN9G_Init();
  if (!EPD_2IN9G_HasError()) EPD_2IN9G_Display(frame);
  if (!EPD_2IN9G_HasError()) EPD_2IN9G_Sleep();
  if (EPD_2IN9G_HasError()) {
    lastError = "display_busy_timeout";
    nextFetchAt = millis() + 180000;
    report("display_failed");
    return;
  }
  lastHash = hash;
  drawnServerHash = receivedServerHash;
  redrawRequested = false;
  lastDrawAt = millis();
  displayed = true;
  ++displayCount;
  report("display_complete");
}

void updateDisplay() {
  HTTPClient http;
  lastHttp = 0;
  lastBytes = 0;
  http.setConnectTimeout(8000);
  http.setTimeout(12000);
  if (!http.begin(config.frameUrl)) { lastError = "invalid_url"; report("fetch_failed"); return; }
  const char *headers[] = {"X-Matchday-Ink-Fresh-For", "X-Matchday-Ink-Poll-After"};
  http.collectHeaders(headers, 2);
  lastHttp = http.GET();
  bool ok = false;
  uint32_t freshFor = 0;
  uint32_t pollSeconds = matchdayInkPollSeconds(config.refreshSeconds, 0);
  if (lastHttp == HTTP_CODE_OK && http.getSize() == sizeof(frame)) {
    auto *stream = http.getStreamPtr();
    stream->setTimeout(12000);
    lastBytes = stream->readBytes(incoming, sizeof(incoming));
    ok = lastBytes == sizeof(frame);
    long parsed = http.header("X-Matchday-Ink-Fresh-For").toInt();
    if (parsed > 0 && parsed <= 86400) freshFor = parsed;
    pollSeconds = matchdayInkPollSeconds(config.refreshSeconds, http.header("X-Matchday-Ink-Poll-After").toInt());
  }
  http.end();
  if (!ok) {
    lastError = lastHttp == HTTP_CODE_OK ? "invalid_frame" : "http_error";
    linkAvailable = false;
    statusPending = haveFrame;
    nextFetchAt = millis() + 60000;
    report("fetch_failed");
    return;
  }
  memcpy(frame, incoming, sizeof(frame));
  receivedServerHash = checksum(frame, sizeof(frame));
  haveFrame = true;
  nextFetchAt = millis() + pollSeconds * 1000UL;
  linkAvailable = true;
  freshUntilAt = millis() + freshFor * 1000UL;
  freshnessKnown = freshFor > 0;
  saveCachedFrame(checksum(frame, sizeof(frame)));
  lastError = "";
  report("data_received");
  presentFrame();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  loadCachedFrame();
  Preferences store;
  if (store.begin("matchdayInk", true)) {
    if (store.getBytesLength("network") == sizeof(config)) {
      store.getBytes("network", &config, sizeof(config));
      configured = config.magic == CONFIG_MAGIC && config.ssid[0] && config.frameUrl[0] &&
                   (config.refreshSeconds == 0 ||
                    (config.refreshSeconds >= 180 && config.refreshSeconds <= 86400));
    }
    store.end();
  }
  if (configured) startWifi();
  else report("setup_required");
}

void loop() {
  readCommands();
  pollScan();
  if (!configured) { delay(5); return; }
  bool connected = WiFi.status() == WL_CONNECTED;
  if (connected && !wasConnected) {
    lastError = "";
    nextFetchAt = 0;
    report("wifi_connected");
  } else if (!connected && wasConnected) {
    linkAvailable = false;
    statusPending = haveFrame;
    lastError = "wifi_disconnected";
    report("wifi_disconnected");
  }
  wasConnected = connected;
  if (!connected) {
    if (millis() - lastWifiAttempt >= 30000) {
      WiFi.reconnect();
      lastWifiAttempt = millis();
      statusPending = haveFrame;
      lastError = "wifi_not_connected";
      report("wifi_retry");
    }
  } else if (refreshRequested || (int32_t)(millis() - nextFetchAt) >= 0) {
    refreshRequested = false;
    nextFetchAt = millis() + matchdayInkPollSeconds(config.refreshSeconds, 0) * 1000UL;
    updateDisplay();
  }
  if (haveFrame && (dataFresh() != observedFresh || (linkAvailable && connected) != observedLink)) {
    observedFresh = dataFresh(); observedLink = linkAvailable && connected; statusPending = true;
  }
  if (statusPending && (!displayed || millis() - lastDrawAt >= 180000)) presentFrame();
  delay(5);
}
