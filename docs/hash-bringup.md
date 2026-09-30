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
- SSD1309 PlatformIO build passes. The first USB flash and startup diagnostic
  flash succeeded after wiring. Camera initialized and returned a 3,656-byte
  JPEG; the OLED remains blank and gives I2C NACK at both 0x3C and 0x3D.
  Display wiring/interface inspection is the next step. Speaker/mic not yet tested.

These do not prove physical OLED, microphone or speaker acceptance.
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
Status 0 means an ACK; observed status 2 at both display addresses means neither
address acknowledged. This is not proof of a broken panel: inspect its power,
ground, SDA/SCL connections and whether the module is configured for I2C.

With USB disconnected, check OLED VCC→3V3, GND→GND, SDA→D4 and SCL→D5 by the
actual printed pin labels. Confirm header joints are soldered if the board was
supplied with loose headers. Obtain a photo of the OLED connector and XIAO
connections before choosing a different display driver or changing power.
The serial console works after the startup delay; opening a serial client can
reset this board, so wait for the USB-only startup line before sending commands.
