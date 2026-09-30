"""Small native OpenClaw operator client. No provider or shared gateway secrets.

Enrollment is separate; runtime uses a signed device identity and its issued
read/write token. These scopes are gateway-wide, not a per-session sandbox.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import ssl
from pathlib import Path
import tempfile
import time
import uuid
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from websockets.sync.client import connect
from . import config

SCOPES = ["operator.read", "operator.write"]
CLIENT = {"id": "cli", "displayName": "Desk Robot", "version": "0.1.0", "platform": "linux", "mode": "cli"}


class GatewayError(RuntimeError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def save_identity(path: Path, identity: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(identity, out)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_identity(path: Path, create=False) -> dict:
    if not path.exists():
        if not create:
            raise GatewayError("Hash device is not enrolled; run the enrollment helper")
        key = Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        identity = {"id": hashlib.sha256(public).hexdigest(), "publicKey": b64(public),
                    "privateKey": b64(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()))}
        save_identity(path, identity)
    if path.stat().st_mode & 0o077:
        raise GatewayError("Hash identity must be private (chmod 600)")
    return json.loads(path.read_text())


def connect_params(identity: dict, challenge: dict, token: str) -> dict:
    ts, nonce = challenge.get("ts"), challenge.get("nonce")
    if type(ts) is not int or ts < 0 or not isinstance(nonce, str) or not nonce:
        raise GatewayError("Invalid Hash authentication challenge")
    payload = "|".join(["v3", identity["id"], CLIENT["id"], CLIENT["mode"], "operator",
                        ",".join(SCOPES), str(ts), token, nonce, "linux", ""])
    key = Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(identity["privateKey"] + "=="))
    return {"minProtocol": 4, "maxProtocol": 4, "client": CLIENT, "role": "operator",
            "scopes": SCOPES, "caps": [], "auth": {"token": token},
            "device": {"id": identity["id"], "publicKey": identity["publicKey"],
                       "signature": b64(key.sign(payload.encode())), "signedAt": ts, "nonce": nonce}}


class HashConnection:
    def __init__(self, url: str, identity_path: Path, bootstrap_token: str | None = None):
        parsed = urlsplit(url)
        if parsed.scheme != "wss" and not (parsed.scheme == "ws" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise GatewayError("Hash requires verified WSS (or a loopback tunnel)")
        self.url, self.path = url, identity_path
        self.identity = load_identity(identity_path, create=bootstrap_token is not None)
        if self.identity.get("gateway") not in {None, url}:
            raise GatewayError("Device identity belongs to a different gateway")
        self.token = bootstrap_token or self.identity.get("token")
        if not self.token:
            raise GatewayError("Hash device has no issued token; complete enrollment")
        self.ws = None
        self.pending = []

    def __enter__(self):
        tls = None
        if self.url.startswith("wss:"):
            cafile = Path(config.HASH_CA_FILE).expanduser() if config.HASH_CA_FILE else None
            tls = ssl.create_default_context(cafile=str(cafile) if cafile else None)
            # Explicitly provisioned leaf certificate may be the trust anchor.
            # Hostname, signature and expiry checks stay enabled.
            if cafile:
                tls.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        self.ws = connect(self.url, ssl=tls, open_timeout=10, close_timeout=2, max_size=8 * 1024 * 1024, proxy=None)
        try:
            challenge = json.loads(self.ws.recv(timeout=10))
            if challenge.get("event") != "connect.challenge":
                raise GatewayError("Expected Hash authentication challenge")
            hello = self.rpc("connect", connect_params(self.identity, challenge["payload"], self.token))
            scopes = hello.get("auth", {}).get("scopes", [])
            if set(scopes) != set(SCOPES):
                raise GatewayError("Hash granted unexpected scopes")
            issued = hello.get("auth", {}).get("deviceToken")
            if issued:
                self.identity.update(token=issued, scopes=scopes, gateway=self.url)
                save_identity(self.path, self.identity)
            return self
        except BaseException:
            self.ws.close()
            raise

    def __exit__(self, *_):
        if self.ws:
            self.ws.close()

    def send(self, method, params):
        request_id = str(uuid.uuid4())
        self.ws.send(json.dumps({"type": "req", "id": request_id, "method": method, "params": params}))
        return request_id

    def rpc(self, method, params, timeout=15):
        request_id = self.send(method, params)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = json.loads(self.ws.recv(timeout=max(.01, deadline - time.monotonic())))
            if msg.get("type") == "res" and msg.get("id") == request_id:
                if not msg.get("ok"):
                    err = msg.get("error", {})
                    raise GatewayError(err.get("message", "Hash rejected request"), err.get("details"))
                return msg.get("payload", {})
            self.pending.append(msg)
        raise GatewayError("Hash request timed out")

    def receive(self, timeout=.2):
        if self.pending:
            return self.pending.pop(0)
        return json.loads(self.ws.recv(timeout=timeout))


def message_text(message):
    content = (message or {}).get("content", [])
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if p.get("type") == "text")
