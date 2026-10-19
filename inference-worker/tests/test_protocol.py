from __future__ import annotations

import io
import json
import unittest

from reversewarp_worker.protocol import ProtocolError, parse_request, serve


class ProtocolTests(unittest.TestCase):
    def test_accepts_health_request(self) -> None:
        request = parse_request(
            '{"version":1,"requestId":"health-1","operation":"health"}'
        )
        self.assertEqual(request.request_id, "health-1")
        self.assertEqual(request.operation, "health")

    def test_rejects_extra_fields(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "request fields"):
            parse_request(
                '{"version":1,"requestId":"x","operation":"health","path":"C:/secret"}'
            )

    def test_rejects_unknown_operation(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "unsupported operation"):
            parse_request('{"version":1,"requestId":"x","operation":"shell"}')

    def test_serve_returns_machine_readable_error(self) -> None:
        source = io.StringIO("not-json\n")
        destination = io.StringIO()
        serve(source, destination, device_info={"kind": "cuda"})
        result = json.loads(destination.getvalue())
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()

