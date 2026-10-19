from __future__ import annotations

import base64
import json
import unittest

from reversewarp_worker.live import LiveWorkerError, parse_frame_request


class LiveProtocolTests(unittest.TestCase):
    def test_accepts_bounded_frame(self) -> None:
        payload = b"jpeg bytes"
        request = json.dumps({"frame": base64.b64encode(payload).decode("ascii")})
        self.assertEqual(parse_frame_request(request), payload)

    def test_rejects_extra_fields(self) -> None:
        with self.assertRaises(LiveWorkerError):
            parse_frame_request('{"frame":"","path":"secret"}')

    def test_rejects_invalid_base64(self) -> None:
        with self.assertRaises(LiveWorkerError):
            parse_frame_request('{"frame":"not base64"}')


if __name__ == "__main__":
    unittest.main()
