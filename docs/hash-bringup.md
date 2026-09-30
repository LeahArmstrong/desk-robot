# Hash-backed stationary desk robot

The ESP32 handles the camera, microphone, OLED and speaker. The Python service
on Omarchy handles speech recognition, synthesis and the device link. Hash main
handles conversation and image understanding through its existing subscription
harness. This fork retains upstream's firmware/protocol and adds a native Hash
WebSocket backend with signed device authentication, image attachments, streamed
replies, expression decoding and run cancellation.

## Current checkpoint

Software acceptance on 2026-09-30:

- Hash read a random six-character code and identified two shapes in an image.
  Seven response deltas and the `happy` OLED expression were decoded. First
  delta 16.883 s, completion 17.767 s; warm follow-up 8.054/8.730 s.
- Gateway transcript/trajectory identifies `gpt-5.6-sol`, Codex app-server,
  the configured OpenAI subscription profile and one image submitted.
- A named run was cancelled through `chat.abort` with `aborted: true`.
- Read/write device authentication passed; empty `config.patch` was rejected
  for missing `operator.admin`. `config.get` is readable and is not a useful
  negative control on the installed version.
- Local espeak-ng → 16 kHz PCM and synthetic speech → Whisper transcription
  passed. Whisper, Silero and Smart Turn models are cached locally.
- Nineteen tests pass, including a real headless service and simulated ESP32
  that receives expression JSON and PCM speech, then shuts down on SIGTERM.
- SSD1309 hardware-I2C build and upload pass. With only USB and the OLED
  directly connected to XIAO pins, the panel ACKs at 0x3C. Owner confirms smooth
  neutral/happy/surprised animations; the banded/shutter redraw is gone.
  Frame rendering measured 31.5–32.1 ms against a 33 ms target. Camera still
  captures JPEGs (4,352 bytes in this test). The amp/speaker were subsequently
  reconnected, but there is still no clearly audible test tone. The owner
  isolated the buzz to the connected OLED; it disappears with the OLED removed.

OLED visible-render acceptance now passes. Physical microphone and speaker
acceptance remain pending.
This is an owner-operated bench prototype, with no installed background unit.
The 8–18 s observed response time remains a tuning item.

## Install and configure

Use Python 3.13 (the tested upstream baseline); Omarchy's system Python is 3.14.
Install espeak-ng and portaudio using the host's package manager, then:

```sh
cd server
uv venv --python 3.13
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Set `BRAIN_BACKEND=hash`, `HASH_URL` and `HUMAN_NAME` in `.env`. Generate a random
`ROBOT_TOKEN` directly into this private file; use the same token in the firmware
when enabling Wi-Fi. Leave Fish Audio and model API keys empty. Set
`LISTEN_ON_START=0` for initial bench work; the interactive `listen` command
enables speech recognition and wake processing later. Once the robot connects,
the current protocol starts local microphone and camera streaming to Omarchy;
frames reach Hash only when requested for vision.

`HASH_IDENTITY_FILE` defaults to `~/.local/share/desk-robot/hash-device.json`.
`HASH_CA_FILE` defaults to `~/.local/share/desk-robot/hash-tls.pem`. For the private
homelab certificate, provision the public leaf certificate through an already
trusted cluster connection; the client trusts that explicit anchor while still
checking hostname and expiry. It never uses TLS verification bypass. For a
publicly trusted gateway, export `HASH_CA_FILE=` to use the system CA store.

The owner runs `.venv/bin/python enroll_hash.py` after provisioning that public
certificate. The helper uses owner kubectl access solely for bootstrap, verifies
the exact pending device ID/scopes, and approves it. The shared gateway secret
exists only in process memory; the file stores the private device identity and
its separately issued token. Routine operation never invokes kubectl.

**Authority:** `operator.read` and `operator.write` are gateway-wide. They exclude
administration and pairing but can reach other permitted sessions and agent
tools. The prompt requests conversation-only behavior; that is not enforcement.
Use this as a trusted personal bench client. Keep identity material outside Git
and do not install it under an untrusted service identity or expose the console.
Speech/text sent to Hash and requested camera frames reach its cloud model.

## Software checks

```sh
cd server
.venv/bin/python -m unittest discover -s tests
.venv/bin/python hash_smoke.py  # real Hash inference; no microphone or robot
.venv/bin/python -m brain.main
```

The live console is http://localhost:8766. Use `ask` for conversation, `say` for
local speech without inference, and `emo happy` for display commands. Runtime
defaults to `agent:main:desk-robot`, a separate conversation under Hash main;
set `HASH_SESSION_KEY` to another `agent:main:desk-robot-...` key for a fresh one.
It is not Hash's primary chat, but remains visible in the same gateway.
`HEADLESS=1` keeps the service alive with closed stdin and handles SIGTERM.
No autostart service is installed yet.

Python movement controls are disabled/rejected, and model instructions describe
a fixed camera. Inherited firmware serial movement commands still drive the
unwired servo pins; leave them unused. Only firmware-known expressions are sent to the OLED. Connection failure
produces a short apology and no automatic re-submission. A timeout/interruption
requests abort for the exact run; loss of the connection may prevent confirmation.

## Bench sequence

1. Check wiring against [the diagram](hardware/wiring.svg) and
   [Seeed's pinout](hardware/xiao-esp32s3-pinout.png). OLED VCC → 3V3, SDA → D4,
   SCL → D5. Amp VIN → 5V, BCLK → D0, LRC → D1, DIN → D2. Common ground;
   capacitor positive → 5V, stripe → ground. Leave D3/D6, SD and battery unwired.
   Confirm the clone amp's pin labels before power; the drawing isn't a bench test.
2. With Leah's wiring confirmation, connect USB and identify the XIAO using
   `pio device list`. Run `cd /home/leah/Work/desk-robot/firmware`, then build with `pio run -e xiao_ssd1309`; upload only to the
   confirmed port. Leave `include/secrets.h` absent for USB-only testing (relative to firmware/).
3. Open the firmware serial console at 115200 baud on that confirmed port
   (`pio device monitor --port <confirmed-port> --baud 115200`). Send `demo off`,
   `emo happy`, `emo surprised`, `blink` and check orientation on the actual OLED.
   These are firmware serial commands; the Python service has no USB transport.
   Change SSD1309 variant/rotation only if this test requires it.
4. Prepare the ignored `secrets.h` using its example, the 2.4 GHz network, the
   actual Omarchy LAN address and matching robot token. Rebuild and flash, then
   verify authenticated Wi-Fi/WebSocket connection. Do not copy credentials into
   a chat, issue, commit or serial screenshot.
5. Run `say hello` and verify the physical speaker without brownouts. Enable
   `listen`; test “hey Rocky” and a spoken question. Then ask “what do you see?”
   while showing an object. Confirm sound, visual grounding and face expression.

The OLED firmware renders animated eyes and seven expressions. This does not
implement arbitrary text, custom graphics or model-generated display layouts.

The supplied pinout is a Seeed reference; source:
https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/ . Its physical pin order
agrees with the imported handoff wiring diagram. D7 is not marked ADC-capable;
camera revision, power peaks and OLED constructor still require bench evidence.

## First USB bench checkpoint

The XIAO enumerates as Espressif USB Serial/JTAG, serial `7C:4F:AD:1F:6E:C8`,
currently `/dev/ttyACM0`. Prefer the matching `/dev/serial/by-id/` path and
re-identify it before upload. Chip detection reports ESP32-S3 rev 0.2, 8 MB PSRAM.
The startup diagnostics print memory, OLED ACK status and initialization stages.
Status 0 means an ACK; the initial status 2 meant neither address acknowledged.
After the owner corrected supply wiring, hardware I2C returned status 5 (timeout).
Both lines read high with pull-ups after releasing Wire. The software-I2C build
boots fully and camera capture still passes; the panel initially stayed blank; see the direct-wiring update below.

The supplied HiLetgo product image identifies `2.42OLED-IIC VER:1.1`, with
a note meaning "For ACK response, short D2." A missing ACK therefore does not
prove absent wiring or a damaged panel. The no-ACK diagnostic used U8g2 `NONAME0_F_SW_I2C` on SCL=D5/SDA=D4.
It is now an optional `xiao_ssd1309_noack` build, not the default: after direct
rewiring this panel ACKs normally and renders smoothly with hardware I2C.
The fallback ignores ACK and releases Wire after the scan, but redraw is slower. Leave the
D2 solder jumper untouched; hardware SH1106 I2C remains the upstream option.
The printed 0x78/0x7A are 8-bit address bytes, equivalent to 7-bit 0x3C/0x3D.

[HiLetgo's listing](https://www.amazon.com/dp/B0CFF5SD1T) specifies a 3–5 V supply.
That does not establish 5 V signal compatibility with the ESP32. This build
continues to supply the panel from 3V3; prior VDD=5V alone is not proof of damage.

With USB disconnected, check OLED VCC→3V3, GND→GND, SDA→D4 and SCL→D5 by the
actual printed pin labels. Confirm header joints are soldered if the board was
supplied with loose headers. The owner confirms the OLED header is soldered. The visible empty pads in the
front photos must not be treated as evidence of an unsoldered active header.
Four direct OLED-to-XIAO wires subsequently restored communication; see
Direct-wiring acceptance below. The original wiring fault was not isolated.
The serial console works after the startup delay; opening a serial client can
reset this board, so wait for the USB-only startup line before sending commands.

## Direct-wiring acceptance

The owner rebuilt the wiring with only USB and the OLED connected directly to
XIAO pins. Software-I2C eye animations appeared but horizontal bands redrew in
sequence. After reseating USB, the same device enumerated again; a fresh scan
confirmed ACK at **0x3C**, no ACK at 0x3D. The pictured optional D2 ACK jumper
was therefore not a reason to require software I2C on this physical board.

The default `xiao_ssd1309` profile now uses hardware I2C at 400 kHz. The owner
confirmed smooth animations and no shutter effect after neutral/happy/surprised
commands. `renderstats` reported 31,504–31,941 us last-frame times, worst
32,124 us in the sampled windows, against 33,000 us target. It measures drawing
plus transfer, not the panel's internal refresh. Camera still captures frames.
The specific original wiring fault was not isolated; the direct rewire fixed
communication, then faster transport fixed visible banding. Do not infer that
5 V destroyed the panel or that its header was unsoldered.

Keep OLED GND→GND, VDD→3V3, SCL→D5, SDA→D4. The amp/speaker were subsequently reconnected; see the audio checkpoint below. Wi-Fi remains
unconfigured. Use `pio run -j 2 -e xiao_ssd1309` for bounded build parallelism;
an unrestricted build archiver was killed with Error -9, and the two-job retry
passed. The no-ACK fallback remains separately selectable for diagnosis only.

## Audio checkpoint — no confirmed tone; buzz isolated to display

After the owner reconnected the amp/speaker, 0.4-second 440 Hz `beep` tests at
volume 0.15 and 0.4 produced no audible tone. Three spaced repetitions at 0.4
also produced no tone. The buzz was initially attributed to the speaker, but
the owner subsequently confirmed it disappears when all four OLED wires are
disconnected. Do not treat that buzz as evidence of speaker activity or damage.
Repeated full-firmware tests after rewiring still gave no clearly audible tone.

Owner meter checks: approximately 5 V at the XIAO and amplifier supply,
continuity through power/ground and BCLK D0, LRC D1, DIN D2, and 4 ohms across
the disconnected speaker leads. The speaker wires were reseated in the screw
terminals. These checks found no open circuit but do not verify I2S waveforms
or acoustic output. Disconnect USB before touching wiring; speaker output
minus must not connect to ground. Leave amp SD and GAIN unconnected.

The firmware now checks speaker buffer allocation, I2S driver/pin setup, task
creation and I2S start, and exposes `audiostats` (USB or existing command path).
Observed: ready=1, I2S1 BCLK=GPIO1/D0, LRC=GPIO2/D1, DIN=GPIO3/D2,
buffer=1,048,576 bytes. Each test queued 12,800 mono bytes and submitted 25,600
stereo bytes to I2S; errors=0, lastError=0, underruns=0, speaking=0 afterward.
These are software/driver receipts, not electrical or acoustic proof. Do not
claim the amp or speaker works because `beep` printed or DMA accepted samples.

### Standalone audio diagnostic

`xiao_audio_only` selects only `firmware/src/audio_only.cpp`. Normal robot
profiles exclude that file. It initializes serial and I2S1 directly, without
camera, microphone, OLED, servos, Wi-Fi or the application's speaker buffer/task.
After identifying the actual USB device and owner confirmation of wiring:

```sh
cd /home/leah/Work/desk-robot/firmware
pio run -j 2 -e xiao_audio_only
pio run -j 2 -e xiao_audio_only -t upload --upload-port <confirmed-port>
```

At 115200 baud, wait for `audio-only: READY`, then send `tone`. It sends one
two-second 440 Hz sine wave on both stereo channels at 16 kHz, 16-bit, peak
3200/32767 (the same peak as integrated `beep` at volume 0.4), with short ramps.
It reports transfer/stop errors and submitted bytes; `status` reports readiness.
There is no automatic tone on boot and no application/network command support.
Expected transfer is 128,000 stereo bytes; driver success is still not sound
acceptance. Keep the OLED disconnected during this isolation test.

To restore eyes and the application after diagnosis, unplug USB before
reconnecting the OLED, then upload `xiao_ssd1309` to the confirmed port.
Do not change GAIN or firmware pin assignments to mask an unverified connection.

Standalone audio bench result (2026-09-30): build and upload passed; serial
reported READY, submitted=128000 expected=128000 driverOK=1, then ready=1.
Owner confirms no sound from this standalone test. Next measure amp SD-to-GND
DC voltage to check shutdown state; no more tones are running. The flashed profile is xiao_audio_only;
normal robot features are unavailable until xiao_ssd1309 is restored.
Build log: /tmp/desk-robot-audio-only-build.log; upload:
/tmp/desk-robot-audio-only-flash.log.
