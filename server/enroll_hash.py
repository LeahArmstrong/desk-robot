"""Owner-run pairing. Shared token stays in memory; only device token persists."""
import json
import subprocess
from pathlib import Path

from brain import config
from brain.hash_transport import GatewayError, HashConnection, load_identity


def kubectl(*args):
    result = subprocess.run(["kubectl", "-n", "openclaw", "exec", "deploy/openclaw", "-c", "openclaw", "--", *args],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError("Owner gateway command failed; no credentials were printed")
    return result.stdout


def enroll(path, identity):
    token = kubectl("node", "-e", "process.stdout.write(process.env.OPENCLAW_GATEWAY_TOKEN || '')").strip()
    if not token:
        raise RuntimeError("Gateway bootstrap token unavailable")
    try:
        with HashConnection(config.HASH_URL, path, token):
            pass
    except GatewayError as exc:
        request_id = exc.details.get("requestId")
        if not request_id:
            raise
        pending = json.loads(kubectl("openclaw", "devices", "list", "--json"))
        request = next((r for r in pending.get("pending", []) if r.get("requestId") == request_id), None)
        if not request or request.get("deviceId") != identity["id"]:
            raise RuntimeError("Pairing request does not match this robot identity")
        if set(request.get("scopes", [])) != {"operator.read", "operator.write"}:
            raise RuntimeError("Pairing request has unexpected scopes")
        kubectl("openclaw", "devices", "approve", request_id, "--json")
        with HashConnection(config.HASH_URL, path, token):
            pass


def main():
    path = Path(config.HASH_IDENTITY_FILE).expanduser()
    identity = load_identity(path, create=True)
    if not identity.get("token"):
        enroll(path, identity)
    with HashConnection(config.HASH_URL, path) as gateway:
        try:
            gateway.rpc("config.patch", {})
        except GatewayError as exc:
            if "missing scope: operator.admin" not in str(exc).lower():
                raise
        else:
            raise RuntimeError("Negative control failed: config.patch unexpectedly allowed")
    print("Desk Robot paired; signed device read/write access passed, admin config access rejected.")


if __name__ == "__main__":
    main()
