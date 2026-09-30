# Desk robot fork

Upstream: cgro00/desk-robot, baseline v1.0 / 3461476 (MIT).
This fork runs a stationary SSD1309 robot with Hash as its conversation backend.
Read `docs/hash-bringup.md` before changing or running it.

- Firmware, Python code and hardware instructions belong here. Host deployment,
  gateway policy, credential lifecycle and inventory belong in ../homelab.
- Preserve upstream history and its selectable SH1106 profile.
- Default backend is Hash's signed-device WebSocket protocol. No provider API
  keys, copied subscription OAuth credentials or owner gateway token at runtime.
- The read/write device grant is gateway-wide. A dedicated session and prompt
  are not a sandbox. Do not describe this bench prototype as restricted to chat.
- Never print `.env`, `secrets.h`, the identity private key or issued tokens.
- No flash until Leah confirms the bench wiring and `pio device list` identifies
  the actual XIAO. No serial device name is assumed.
- OLED uses 3V3; amp uses 5V; common ground. No servos are fitted.
- Tests: `cd server && .venv/bin/python -m unittest discover -s tests`.
  The device-service test needs espeak-ng and binds temporary local ports.
  `hash_smoke.py` makes a real subscription-backed Hash turn; do not run in CI.
- Build only: `cd firmware && pio run -e xiao_ssd1309`.
- Do not enable public ingress, change Hash's global model or grant robot admin
  scopes as a workaround for a failed integration test.
