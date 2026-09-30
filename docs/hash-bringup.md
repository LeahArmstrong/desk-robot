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
  reconnected. A crackling tone occurred while the owner held a jumper against
  amp DIN; a repeat was silent. After amp solder reflow, a tone played with
  heavy static. Clean, repeatable sound is still pending. The owner isolated the earlier buzz to the connected OLED; it disappears with the OLED removed.

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

## Audio diagnosis — tone after solder reflow; clean playback pending

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
Owner confirms no sound from this standalone test. SD-to-GND measures 0.48 V
(owner meter reading), within the enabled stereo-average range; shutdown is
not indicated. Owner swapped in a spare MAX98357A with the same speaker/wires and OLED
disconnected. The repeated two-second tone again submitted 128,000 bytes with
driverOK=1, but the owner heard nothing. The 0.48 V SD reading was from the
first amp; the replacement has not been metered. Clock/data waveforms remain
unmeasured. Owner meter is Southwire 10040N: AC volts specified 50–400 Hz; frequency
sensitivity >8 V RMS, so 3.3 V I2S frequency readings are not guaranteed;
speaker terminals carry bridge-tied class-D switching, not clean analog audio. No more tones are running. The flashed profile is xiao_audio_only;
normal robot features are unavailable until xiao_ssd1309 is restored.
Build log: /tmp/desk-robot-audio-only-build.log; upload:
/tmp/desk-robot-audio-only-flash.log.

Volume comparison: added serial `louder` to the standalone diagnostic only.
It sends the same 2-second 440 Hz tone at peak 8000/32767 (2.5 times the default
3200 peak, +8 dB). No GAIN wiring changes. Flashed and sent once: submitted
128000, driverOK=1; owner confirms still no sound. Build/upload evidence:
`/tmp/desk-robot-audio-louder-flash.log`. Default `tone` remains at peak3200. Volume increase did not restore sound.
Meter specifications: [Southwire 10040N manual, printed pp.15–16](https://assets.unilogcorp.com/187/ITEM/DOC/Southwire_102725405_Instruction_Installation_Manual.pdf).

Timed clock check: standalone `clocks` sends **zero-valued audio for 30 seconds**,
then stops I2S. It is silent and does not run on boot. With the meter in DC volts,
black at amp GND and red on BCLK or LRC (not speaker outputs), a roughly 50%-duty
3.3 V clock is expected to average near 1.65 V. This is only a coarse activity
check: even an expected voltage does not prove frequency, timing or valid data.
Expected digital rates are BCLK512kHz and LRC16kHz, but the owner's meter is not
specified for measuring frequency at these logic amplitudes. Clock mode ran for 30 seconds (1,920,000 bytes, driverOK=1). Owner
measured LRC-to-GND at 1.65 V. A later separate run also measured BCLK-to-GND
at 1.65 V; DIN was subsequently probed; the recalled voltage was uncertain, as recorded below. The brief BCLK reading described as
"a few hundred" had no unit recorded and must not be treated as hundreds of volts. Build/upload log:
`/tmp/desk-robot-audio-clocks-flash.log`.

Owner supplied purchase screenshots: AITRIP three-pack MAX98357A soldered
modules and DWEII four-pack 4-ohm 3 W speakers. Reopened Amazon page displays
an 8-ohm variation and says a different variation was purchased; that page does
not establish that the delivered speaker differs from the order. Owner earlier
measured 4 ohms across the disconnected speaker leads.

At owner request, standalone `high` adds a two-second 440 Hz tone at peak
16000/32767 (48.8% digital full scale, twice `louder` amplitude). It does not
change default `tone`, `louder`, amp GAIN or wiring. Build/upload passed
(`/tmp/desk-robot-audio-high-flash.log`), then high submitted128000 driverOK1.
Owner confirmed the high test remained silent. BCLK measurement was deferred
for the explicitly requested full-scale test below, then completed as recorded above.

Owner then explicitly requested a full-volume check before the next clock
measurement. Added `full`: one second of 440 Hz at peak32767/32767, with the
same short ramps. Build/upload passed (`/tmp/desk-robot-audio-full-flash.log`);
64,000 stereo bytes submitted, driverOK=1. Owner reports a click or faint
sound, not a confirmed sustained tone; idle again afterward. No automatic playback at boot, no GAIN changes.

The independent speaker movement check was completed: owner reports noise
when attached to an AA battery. This confirms basic acoustic response, not
full fidelity. Procedure for reference: unplug
USB, disconnect BOTH speaker leads from the amp, then briefly tap them across
one ordinary 1.5 V AA/AAA cell (red to +, black to -). Expect a small click or
cone twitch on contact/release; remove immediately, do not hold DC on the coil,
and do not use a 9 V or lithium-ion cell. A response establishes movement,
not full audio fidelity. Compare with a spare speaker if uncertain.
[Manufacturer explanation of the 1.5 V speaker test](https://eminence.com/a/faq).

DIN was tested using the standalone
`data` command: 10 seconds of the original low-level 440 Hz tone, peak3200,
then automatic stop. It is not silent clocks: actual audio samples must be
transmitted to distinguish a stuck-low data line from valid silence. Expected
DC average is roughly mid-supply for this signed PCM stream, but the reading
cannot validate bits or timing. Build/upload passed:
`/tmp/desk-robot-audio-data-flash.log`. No tone runs automatically on boot;
other test commands retain their levels/durations.

Latest physical result: the ten-second low-level `data` tone became audible
while the owner probed DIN. The recalled ~3 V reading was uncertain and is not
a validated data waveform measurement. Removing both probes and repeating
made it silent again. Replacing/reseating the DIN jumper through the breadboard
also remained silent. Connecting the jumper to the top of the amp DIN pin,
bypassing the breadboard connection, restored the tone **with crackling**.
Every ten-second run submitted 640,000 bytes with driverOK=1; it was the physical
connection change that distinguished these results. This implicates the
breadboard/header/contact path but does not isolate the exact failed contact
or prove the crackling cause. Neither amplifier nor speaker is proven defective.

A further identical repeat was silent again (640,000 bytes, driverOK=1).
Direct contact has not produced repeatable sound. Owner confirms the successful crackling run required holding/pressing the
jumper against the amp pin. Tone tests stopped. Next USB-off remove the amp
from the breadboard and use snug female sockets on its long underside header
pins, avoiding pressure contact on short top-side soldered ends. Keep the same
pin mapping, speaker and supply capacitor. Await stable hands-free wiring. Keep OLED disconnected and leave GAIN/SD untouched.
Disconnect USB before altering connections. Clear, repeatable sound is required
before restoring normal robot firmware; clean audio acceptance remains open.

Solder-reflow follow-up: owner paused testing, reflowed the amp solder and
reconnected. The unchanged ten-second low-level `data` test submitted640000,
driverOK1; owner reports a tone with heavy static. This is partial acoustic
success, not clean playback or a confirmed root cause. The planned female
connector setup has not yet been tested. Next USB off, amp off breadboard,
snug female sockets on all five long underside header pins: VIN→5V,
GND→common ground, BCLK→D0, LRC→D1, DIN→D2. Keep the same speaker, capacitor
across5V/GND, SD/GAIN unconnected, and OLED disconnected. Retest at the original
low level once owner confirms ready; no further volume escalation is needed.
