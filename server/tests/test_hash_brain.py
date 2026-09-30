import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from brain import config
from brain.hash_brain import HashBrain, SpeechDecoder, request_params
from brain.hash_transport import GatewayError, connect_params, load_identity
from brain.thinking import Interrupted


class DecoderTests(unittest.TestCase):
    def test_split_emotion_and_sentence(self):
        seen = []
        d = SpeechDecoder(seen.append)
        self.assertEqual(d.feed('[hap'), [])
        self.assertEqual(d.feed('py] A green '), [])
        self.assertEqual(d.feed('circle. Another'), ['A green circle.'])
        self.assertEqual(d.feed(' shape.', final=True), ['Another shape.'])
        self.assertEqual(seen, ['happy'])

    def test_unknown_emotion_never_reaches_firmware(self):
        d = SpeechDecoder()
        self.assertEqual(d.feed('[launch] hello', final=True), ['hello'])
        self.assertEqual(d.emotion, 'neutral')

    def test_sentence_limit(self):
        self.assertEqual(len(SpeechDecoder().feed('[happy] One. Two. Three. Four.', final=True)), 3)

    def test_missing_image_is_explicit(self):
        p = request_params('/config set bad true', None, True, 'desk', 'run')
        self.assertNotIn('attachments', p)
        self.assertIn('no fresh frame', p['message'])
        self.assertFalse(p['message'].startswith('/'))
        self.assertNotIn('suppressCommandInterpretation', p)

    def test_image_bound(self):
        with self.assertRaises(ValueError):
            request_params('see', b'a' * (2 * 1024 * 1024 + 1), True, 'desk', 'run')

    def test_signed_challenge_and_private_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'identity.json'
            identity = load_identity(path, create=True)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            params = connect_params(identity, {'nonce': 'nonce', 'ts': 123}, 'token')
            payload = '|'.join(['v3', identity['id'], 'cli', 'cli', 'operator',
                                'operator.read,operator.write', '123', 'token', 'nonce', 'linux', ''])
            Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(identity['publicKey'] + '==')).verify(
                base64.urlsafe_b64decode(params['device']['signature'] + '=='), payload.encode())
            with self.assertRaises(GatewayError):
                connect_params(identity, {'nonce': 'nonce', 'ts': True}, 'token')


class FakeGateway:
    def __init__(self, events=()):
        self.events = iter(events)
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def rpc(self, method, params, **kwargs):
        self.calls.append((method, params))
        return {}
    def receive(self):
        event = next(self.events)
        if isinstance(event, Exception): raise event
        run_id = self.calls[0][1]['idempotencyKey']
        return {'event': 'chat', 'payload': {'runId': run_id, **event}}


class StreamingTests(unittest.TestCase):
    def test_cumulative_final_not_spoken_twice(self):
        g = FakeGateway([{'state':'delta','deltaText':'[happy] Hello. '},
                         {'state':'final','message':{'content':[{'type':'text','text':'[happy] Hello. Bye.'}]}}])
        with patch('brain.hash_brain.HashConnection', return_value=g):
            self.assertEqual(list(HashBrain().reply('hello')), ['Hello.', 'Bye.'])
        self.assertEqual([m for m,_ in g.calls], ['chat.send'])

    def test_cancel_requests_remote_abort(self):
        cancel = threading.Event(); cancel.set()
        g = FakeGateway()
        with patch('brain.hash_brain.HashConnection', return_value=g):
            with self.assertRaises(Interrupted):
                list(HashBrain().reply('hello', cancelled=cancel))
        self.assertEqual(g.calls[-1][0], 'chat.abort')

    def test_failure_never_resubmits(self):
        g = FakeGateway([OSError('connection lost')])
        with patch('brain.hash_brain.HashConnection', return_value=g):
            answer = list(HashBrain().reply('hello'))
        self.assertEqual(sum(m == 'chat.send' for m,_ in g.calls), 1)
        self.assertIn("couldn't complete", answer[0])


if __name__ == '__main__':
    unittest.main()
