"""Mock inventory REST API with switchable failure modes.

Run it with: python -m src.inventory_api
"""

import asyncio
import json
import socket
import threading
import time
from typing import Literal
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import inventory_api_url
from src.db import DATA_DIR

INVENTORY_PATH = DATA_DIR / "mock_inventory.json"
SLOW_DELAY_SECONDS = 5.0  # Longer than the client's default timeout.


class ModeRequest(BaseModel):
    mode: Literal["normal", "outage", "bad_json", "slow"]


def create_app(inventory_path=INVENTORY_PATH, slow_delay=SLOW_DELAY_SECONDS):
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    app = FastAPI(title="Mock Inventory API")
    app.state.mode = "normal"

    @app.get("/inventory")
    async def get_inventory():
        if app.state.mode == "outage":
            return JSONResponse({"detail": "Inventory service unavailable"}, status_code=503)
        if app.state.mode == "bad_json":
            return Response('{"items": [', media_type="application/json")
        if app.state.mode == "slow":
            await asyncio.sleep(slow_delay)
        return inventory

    @app.post("/_admin/mode")
    async def set_mode(request: ModeRequest):
        app.state.mode = request.mode
        return {"mode": app.state.mode}

    return app


class BackgroundServer:
    """Run the API in a background thread, for Colab and tests. Port 0 picks a free port."""

    def __init__(self, app=None, host="127.0.0.1", port=0):
        self._socket = socket.socket()
        self._socket.bind((host, port))
        self.url = f"http://{host}:{self._socket.getsockname()[1]}"
        self._server = uvicorn.Server(uvicorn.Config(app or create_app(), log_level="warning"))
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._socket]}, daemon=True
        )

    def start(self, wait_seconds=5.0):
        self._thread.start()
        deadline = time.monotonic() + wait_seconds
        while not self._server.started:
            if time.monotonic() > deadline or not self._thread.is_alive():
                self.stop()
                raise RuntimeError("The inventory API did not start")
            time.sleep(0.01)
        return self

    def stop(self):
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join()
        self._socket.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc_info):
        self.stop()


if __name__ == "__main__":
    address = urlsplit(inventory_api_url())
    uvicorn.run(create_app(), host=address.hostname, port=address.port)
