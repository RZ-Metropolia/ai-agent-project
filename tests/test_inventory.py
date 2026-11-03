"""Tests for the mock inventory API and its client.

Run from the project root: python -m unittest discover tests
"""

import json
import time
import unittest

import httpx
from fastapi.testclient import TestClient

from src.inventory_api import INVENTORY_PATH, BackgroundServer, create_app
from src.inventory_client import InventoryClient, InventoryUnavailable, set_inventory_mode

INVENTORY = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


class InventoryApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(slow_delay=0))
        self.addCleanup(self.client.close)

    def set_mode(self, mode):
        return self.client.post("/_admin/mode", json={"mode": mode})

    def test_normal_mode_returns_the_inventory_file(self):
        response = self.client.get("/inventory")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), INVENTORY)

    def test_outage_mode_returns_503(self):
        self.set_mode("outage")
        self.assertEqual(self.client.get("/inventory").status_code, 503)

    def test_bad_json_mode_returns_unparsable_body(self):
        self.set_mode("bad_json")
        response = self.client.get("/inventory")
        self.assertEqual(response.status_code, 200)
        with self.assertRaises(ValueError):
            response.json()

    def test_mode_can_be_switched_back(self):
        self.set_mode("outage")
        self.set_mode("normal")
        self.assertEqual(self.client.get("/inventory").status_code, 200)

    def test_unknown_mode_is_refused(self):
        self.assertEqual(self.set_mode("broken").status_code, 422)


class InventoryClientTests(unittest.TestCase):
    def client_for(self, handler):
        return InventoryClient("http://inventory.test", transport=httpx.MockTransport(handler))

    def client_returning(self, body, status_code=200):
        content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return self.client_for(lambda request: httpx.Response(status_code, content=content))

    def assert_unavailable(self, client, reason):
        with self.assertRaises(InventoryUnavailable) as caught:
            client.get_portions()
        self.assertIn(reason, str(caught.exception))

    def test_valid_response_returns_portions_per_item(self):
        client = self.client_returning({"items": [{"item_id": 1, "portions": 8}, {"item_id": 2, "portions": 0}]})
        self.assertEqual(client.get_portions(), {1: 8, 2: 0})

    def test_http_errors_are_unavailable(self):
        for status_code in (404, 500, 503):
            with self.subTest(status_code):
                client = self.client_returning({"items": []}, status_code)
                self.assert_unavailable(client, f"HTTP {status_code}")

    def test_redirect_is_unavailable(self):
        self.assert_unavailable(self.client_returning({"items": []}, 302), "HTTP 302")

    def test_timeout_is_unavailable(self):
        def handler(request):
            raise httpx.ReadTimeout("too slow")

        self.assert_unavailable(self.client_for(handler), "timed out")

    def test_connection_failure_is_unavailable(self):
        def handler(request):
            raise httpx.ConnectError("refused")

        self.assert_unavailable(self.client_for(handler), "could not be reached")

    def test_invalid_data_is_unavailable(self):
        bodies = {
            "not json": b'{"items": [',
            "html": b"<html></html>",
            "missing items": {},
            "items not a list": {"items": 5},
            "missing portions": {"items": [{"item_id": 1}]},
            "negative portions": {"items": [{"item_id": 1, "portions": -1}]},
            "text portions": {"items": [{"item_id": 1, "portions": "5"}]},
            "float portions": {"items": [{"item_id": 1, "portions": 2.5}]},
            "boolean portions": {"items": [{"item_id": 1, "portions": True}]},
            "null portions": {"items": [{"item_id": 1, "portions": None}]},
        }
        for name, body in bodies.items():
            with self.subTest(name):
                self.assert_unavailable(self.client_returning(body), "invalid data")

    def test_duplicate_items_are_unavailable(self):
        body = {"items": [{"item_id": 1, "portions": 8}, {"item_id": 1, "portions": 0}]}
        self.assert_unavailable(self.client_returning(body), "duplicate")


class RealServerTests(unittest.TestCase):
    """The client against a running server over real HTTP."""

    def setUp(self):
        self.server = BackgroundServer(create_app(slow_delay=1.0)).start()
        self.addCleanup(self.server.stop)
        self.client = InventoryClient(self.server.url, timeout=0.2)

    def test_normal_mode(self):
        expected = {row["item_id"]: row["portions"] for row in INVENTORY["items"]}
        self.assertEqual(self.client.get_portions(), expected)

    def test_outage_mode(self):
        set_inventory_mode(self.server.url, "outage")
        with self.assertRaisesRegex(InventoryUnavailable, "HTTP 503"):
            self.client.get_portions()

    def test_bad_json_mode(self):
        set_inventory_mode(self.server.url, "bad_json")
        with self.assertRaisesRegex(InventoryUnavailable, "invalid data"):
            self.client.get_portions()

    def test_slow_mode_stops_at_the_client_timeout(self):
        set_inventory_mode(self.server.url, "slow")
        started = time.monotonic()
        with self.assertRaisesRegex(InventoryUnavailable, "timed out"):
            self.client.get_portions()
        self.assertLess(time.monotonic() - started, 0.9)

    def test_stopped_server_is_unavailable(self):
        url = self.server.url
        self.server.stop()
        # Windows may report a closed port as a timeout, so the reason is not checked here.
        with self.assertRaises(InventoryUnavailable):
            InventoryClient(url, timeout=0.2).get_portions()


if __name__ == "__main__":
    unittest.main()
