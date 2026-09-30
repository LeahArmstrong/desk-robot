// Standalone bench test. Selected ONLY by the xiao_audio_only environment.
// No camera, mic, OLED, servos, Wi-Fi, ring buffer or speaker worker task.
#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

namespace {
constexpr i2s_port_t kPort = I2S_NUM_1;
constexpr int kRate = 16000;
constexpr size_t kFramesPerChunk = 256;
constexpr size_t kToneFrames = kRate * 2;
// Same peak as the integrated test: 8000 * volume 0.4.
constexpr float kPeak = 3200.0f;
bool ready = false;

bool check(esp_err_t result, const char* operation) {
  if (result == ESP_OK) return true;
  Serial.printf("audio-only: %s failed: %s (%d)\n", operation,
                esp_err_to_name(result), result);
  ready = false;
  return false;
}

void tone() {
  if (!ready) {
    Serial.println("audio-only: not ready; no tone sent");
    return;
  }
  if (!check(i2s_zero_dma_buffer(kPort), "clear DMA") ||
      !check(i2s_start(kPort), "start")) return;

  Serial.println("audio-only: tone START 440 Hz, 2 seconds, peak=3200/32767");
  int16_t samples[kFramesPerChunk * 2];
  size_t total = 0;
  bool complete = true;
  for (size_t first = 0; first < kToneFrames; first += kFramesPerChunk) {
    const size_t frames = min(kFramesPerChunk, kToneFrames - first);
    for (size_t i = 0; i < frames; ++i) {
      const size_t frame = first + i;
      // Ten-millisecond ramps keep start/stop clicks out of the test.
      const float envelope = min(1.0f, min(frame / 160.0f,
                                          (kToneFrames - 1 - frame) / 160.0f));
      const int16_t value = static_cast<int16_t>(
          kPeak * envelope * sinf(2.0f * PI * 440.0f * frame / kRate));
      samples[2 * i] = samples[2 * i + 1] = value;
    }
    size_t written = 0;
    const size_t bytes = frames * 2 * sizeof(int16_t);
    const esp_err_t result = i2s_write(kPort, samples, bytes, &written,
                                     pdMS_TO_TICKS(1000));
    total += written;
    if (!check(result, "write") || written != bytes) {
      Serial.printf("audio-only: incomplete write %u/%u bytes\n",
                    static_cast<unsigned>(written), static_cast<unsigned>(bytes));
      complete = false;
      break;
    }
  }
  // Four 256-frame DMA buffers take 64 ms at 16 kHz; allow them to drain.
  delay(100);
  const bool cleared = check(i2s_zero_dma_buffer(kPort), "clear DMA after tone");
  const bool stopped = check(i2s_stop(kPort), "stop");
  Serial.printf("audio-only: tone END submitted=%u expected=128000 driverOK=%d\n",
                static_cast<unsigned>(total), complete && cleared && stopped);
  Serial.println("audio-only: driver receipt only; audible result requires owner confirmation");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  delay(1500);
  Serial.println("audio-only: standalone diagnostic; no automatic tone");

  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  config.sample_rate = kRate;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.bits_per_chan = I2S_BITS_PER_CHAN_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 4;
  config.dma_buf_len = kFramesPerChunk;
  config.tx_desc_auto_clear = true;
  if (!check(i2s_driver_install(kPort, &config, 0, nullptr), "install")) return;

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = 1;       // D0 -> BCLK
  pins.ws_io_num = 2;        // D1 -> LRC
  pins.data_out_num = 3;     // D2 -> DIN
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  if (!check(i2s_set_pin(kPort, &pins), "pins") ||
      !check(i2s_zero_dma_buffer(kPort), "initial clear DMA") ||
      !check(i2s_stop(kPort), "initial stop")) return;
  ready = true;
  Serial.println("audio-only: READY I2S1 16000 Hz stereo 16-bit; BCLK=D0 LRC=D1 DIN=D2");
  Serial.println("audio-only: commands: tone, status");
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command == "tone") tone();
    else if (command == "status") Serial.printf("audio-only: ready=%d\n", ready);
    else if (command.length()) Serial.println("audio-only: commands: tone, status");
  }
  delay(5);
}
