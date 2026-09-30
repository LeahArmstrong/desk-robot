"""Exercise the real headless service against a simulated ESP32 socket."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from websockets.sync.client import connect


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class DeviceServiceTest(unittest.TestCase):
    def test_headless_emotion_audio_and_shutdown(self):
        robot_port, view_port = free_port(), free_port()
        token = secrets.token_hex(32)
        env = dict(os.environ, HEADLESS='1', LISTEN_ON_START='0', HAS_SERVOS='0',
                   ROBOT_TOKEN=token, ROBOT_PORT=str(robot_port), LIVE_VIEW_PORT=str(view_port))
        with tempfile.TemporaryFile(mode='w+') as log:
            p = subprocess.Popen([sys.executable, '-u', '-m', 'brain.main'], stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, env=env, cwd=Path(__file__).resolve().parents[1])
            try:
                url = f'http://127.0.0.1:{view_port}'
                deadline = time.monotonic() + 10
                while True:
                    if p.poll() is not None:
                        log.seek(0); self.fail(log.read())
                    try:
                        with urllib.request.urlopen(url+'/status', timeout=.5) as r:
                            state = json.load(r)
                        break
                    except OSError:
                        if time.monotonic() > deadline: raise
                        time.sleep(.05)
                self.assertFalse(state['has_servos'])
                self.assertFalse(state['listening'])
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1',robot_port),timeout=.5): pass
                        break
                    except OSError:
                        if p.poll() is not None or time.monotonic() > deadline:
                            log.seek(0); self.fail(log.read())
                        time.sleep(.05)
                def post(action, data):
                    request = urllib.request.Request(url+'/api/'+action, json.dumps(data).encode(),
                              {'Content-Type':'application/json', 'X-Rocky-Console':'1'})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return json.load(response)
                with connect(f'ws://127.0.0.1:{robot_port}', proxy=None) as robot:
                    robot.send(json.dumps({'type':'hello','token':token}))
                    # Wait for authenticated initial configuration before asking for output.
                    robot.recv(timeout=5)
                    post('emotion', {'name':'surprised'})
                    post('say', {'text':'The robot speaker path works.'})
                    emotion_seen, audio_bytes, end = False, 0, False
                    until = time.monotonic() + 15
                    while time.monotonic() < until and not end:
                        msg = robot.recv(timeout=5)
                        if isinstance(msg, bytes):
                            self.assertEqual(msg[0], 1)
                            audio_bytes += len(msg)-1
                        else:
                            msg = json.loads(msg)
                            if msg.get('type')=='emotion' and msg.get('name')=='surprised': emotion_seen=True
                            if msg.get('type')=='speak_end':
                                end=True
                                robot.send(json.dumps({'type':'speak_done'}))
                    self.assertTrue(emotion_seen)
                    self.assertTrue(end)
                    self.assertGreater(audio_bytes, 16000)
            finally:
                p.terminate()
                try: p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait()
            self.assertEqual(p.returncode, 0)


if __name__ == '__main__': unittest.main()
