"""Hash conversation backend: image attachment, streamed speech, OLED emotion."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import threading
import time
import uuid

from websockets.exceptions import ConnectionClosed

from . import config
from .hash_transport import GatewayError, HashConnection, message_text
from .thinking import Interrupted, Reply

SENTENCE_END = re.compile(r"(?<=[!?])\s+|(?<=[^.]\.)\s+")


class SpeechDecoder:
    """Buffer split tags/sentences; only firmware-known expressions reach OLED."""
    def __init__(self, on_emotion=None):
        self.buffer = ""
        self.emotion = "neutral"
        self.tag_done = False
        self.count = 0
        self.on_emotion = on_emotion

    def feed(self, text, final=False):
        self.buffer += text
        if not self.tag_done:
            lead = self.buffer.lstrip()
            if not final and (not lead or (lead.startswith("[") and "]" not in lead and len(lead) < 25)):
                return []
            tag = re.match(r"^\s*\[(\w+)\]\s*", self.buffer)
            if tag:
                if tag[1].lower() in config.EMOTIONS:
                    self.emotion = tag[1].lower()
                self.buffer = self.buffer[tag.end():]
            self.tag_done = True
            if self.on_emotion:
                self.on_emotion(self.emotion)
        parts = SENTENCE_END.split(self.buffer)
        self.buffer = "" if final else parts.pop()
        result = []
        for part in parts:
            if part.strip() and self.count < config.REPLY_MAX_SENTENCES:
                result.append(part.strip())
                self.count += 1
        return result


def request_params(question, jpeg, camera_wanted, session_key, run_id):
    if len(question) > 8000:
        raise ValueError("Question too long")
    if jpeg and len(jpeg) > 2 * 1024 * 1024:
        raise ValueError("Camera frame exceeds 2 MiB")
    context = (
        "Desk robot interface: reply in one to three short spoken sentences, no Markdown. "
        "Start with exactly one emotion tag from [neutral], [happy], [sad], [angry], "
        "[surprised], [sleepy], [thinking]. The local service renders that expression. "
        "You are Hash speaking through a stationary robot: it has a fixed camera and no servos. "
        "Do not claim to turn its head or follow faces. Answer this conversation directly; "
        "do not use shell, filesystem, browser, delegation or other tools for this reply. "
        "If an image is attached it is the current supplied frame; describe only what it shows. "
        "This is a voice conversation, not authorization for infrastructure changes. "
    )
    if camera_wanted and not jpeg:
        context += "The camera currently has no fresh frame; say so instead of inventing a view. "
    params = {"sessionKey": session_key, "message": context + "\nSpoken input: " + question,
              "idempotencyKey": run_id, "deliver": False, "thinking": "low",
              "timeoutMs": int(config.HASH_TIMEOUT * 1000)}
    if jpeg:
        params["attachments"] = [{"type": "image", "mimeType": "image/jpeg", "fileName": "camera.jpg",
                                  "content": base64.b64encode(jpeg).decode()}]
    return params


class HashBrain:
    def __init__(self, actions=None):
        self.emotion = "neutral"
        self._active_cancel = None
        self._lock = threading.Lock()
        self.last_receipt = {}

    def abandon(self):
        if self._active_cancel:
            self._active_cancel.set()

    def ask(self, question, jpeg=None, camera_wanted=False):
        return Reply(" ".join(self.reply(question, jpeg, camera_wanted=camera_wanted)), self.emotion)

    def reply(self, question, jpeg=None, on_emotion=None, cancelled=None, camera_wanted=False):
        cancel = cancelled if cancelled is not None else threading.Event()
        if not self._lock.acquire(blocking=False):
            raise GatewayError("Hash is still finishing the previous robot turn")
        self._active_cancel = cancel
        run_id = str(uuid.uuid4())
        started = time.monotonic()
        decoder = SpeechDecoder(on_emotion)
        text = ""
        done = False
        self.last_receipt = {"run_id": run_id, "session_key": config.HASH_SESSION_KEY, "delta_events": 0}
        try:
            with HashConnection(config.HASH_URL, Path(config.HASH_IDENTITY_FILE).expanduser()) as gateway:
                params = request_params(question, jpeg, camera_wanted, config.HASH_SESSION_KEY, run_id)
                try:
                    gateway.rpc("chat.send", params)
                    while time.monotonic() - started < config.HASH_TIMEOUT:
                        if cancel.is_set():
                            raise Interrupted()
                        try:
                            event = gateway.receive()
                        except TimeoutError:
                            continue
                        payload = event.get("payload", {})
                        if event.get("event") != "chat" or payload.get("runId") != run_id:
                            continue
                        state = payload.get("state")
                        if state == "error":
                            raise GatewayError("Hash could not complete this turn")
                        if state == "aborted":
                            done = True
                            raise Interrupted()
                        if state not in {"delta", "final"}:
                            continue
                        if state == "delta":
                            self.last_receipt["delta_events"] += 1
                            self.last_receipt.setdefault("first_delta_seconds", round(time.monotonic() - started, 3))
                            if payload.get("replace"):
                                new_text = payload.get("deltaText", "")
                            elif "deltaText" in payload:
                                new_text = text + payload["deltaText"]
                            else:
                                new_text = message_text(payload.get("message"))
                        else:
                            new_text = message_text(payload.get("message")) or text
                            done = True
                        if not new_text.startswith(text):
                            # Already spoken text cannot be retracted. Fail closed on revisions.
                            raise GatewayError("Hash revised already-streamed text")
                        addition, text = new_text[len(text):], new_text
                        if len(text) > 16000:
                            raise GatewayError("Hash reply exceeded the robot response limit")
                        sentences = decoder.feed(addition, final=done)
                        self.emotion = decoder.emotion
                        for sentence in sentences:
                            if cancel.is_set():
                                raise Interrupted()
                            yield sentence
                        if done:
                            self.last_receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
                            return
                    raise GatewayError("Hash response timed out; it was not resubmitted")
                finally:
                    if not done:
                        try:
                            gateway.rpc("chat.abort", {"sessionKey": config.HASH_SESSION_KEY, "runId": run_id}, timeout=5)
                        except (GatewayError, TimeoutError, ConnectionClosed):
                            pass  # Drop local output even when remote abort cannot be confirmed.
        except (GatewayError, OSError, ConnectionClosed) as exc:
            self.last_receipt["error"] = str(exc)
            self.emotion = "sad"
            if on_emotion:
                on_emotion("sad")
            print(f"(Hash unavailable: {type(exc).__name__}; no automatic retry)")
            yield "I couldn't complete that reply. Please try again."
        finally:
            self._active_cancel = None
            self._lock.release()
