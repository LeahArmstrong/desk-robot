"""Image + streamed text + expression canary, with no robot or audio required."""
import json
from pathlib import Path
import uuid
import cv2
import numpy as np

from brain import config
from brain.hash_brain import HashBrain

config.HASH_SESSION_KEY = "agent:main:desk-robot-smoke-" + uuid.uuid4().hex[:10]
canvas = np.full((240, 540, 3), 255, np.uint8)
cv2.circle(canvas, (100, 105), 65, (0, 160, 0), -1)
cv2.rectangle(canvas, (320, 40), (450, 170), (200, 0, 180), -1)
marker = uuid.uuid4().hex[:6].upper()
cv2.putText(canvas, marker, (165, 225), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
ok, encoded = cv2.imencode(".jpg", canvas)
assert ok
emotions = []
brain = HashBrain()
reply = " ".join(brain.reply("Describe the two colored shapes and read the six-character code in this image. Use a happy expression.",
                             encoded.tobytes(), on_emotion=emotions.append, camera_wanted=True))
print(json.dumps({"reply": reply, "emotions": emotions, "receipt": brain.last_receipt}, indent=2))
assert marker.lower() in reply.lower(), "Image code was not read correctly"
assert "green" in reply.lower() and "circle" in reply.lower(), "Left shape not identified"
assert any(c in reply.lower() for c in ("purple", "magenta", "pink")), "Right color not identified"
assert emotions == ["happy"], "Expression was not delivered"
assert brain.last_receipt["delta_events"] > 0, "No streaming events"
print("PASS: image contents, streaming events and OLED expression decoded")
