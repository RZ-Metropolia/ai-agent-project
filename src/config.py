"""Runtime settings and the context that the tools receive."""

import os
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.db import DB_PATH
from src.inventory_client import InventoryClient

DEFAULT_INVENTORY_API_URL = "http://127.0.0.1:8000"
DEFAULT_INVENTORY_TIMEOUT_SECONDS = 2.0
DEFAULT_TIMEZONE = "Europe/Berlin"
PICKUP_OPEN = time(11, 0)
PICKUP_CLOSE = time(21, 0)


@dataclass(frozen=True)
class ToolContext:
    """What the tools need from their environment. The model never sees or sets these values."""

    db_path: Path
    inventory: InventoryClient
    service_date: date
    timezone: ZoneInfo
    pickup_open: time = PICKUP_OPEN
    pickup_close: time = PICKUP_CLOSE


def inventory_api_url():
    load_dotenv()
    return os.getenv("INVENTORY_API_URL") or DEFAULT_INVENTORY_API_URL


def load_context():
    """Build the context from the environment and an optional .env file."""
    load_dotenv()
    timezone = ZoneInfo(os.getenv("RESTAURANT_TIMEZONE") or DEFAULT_TIMEZONE)
    service_date = os.getenv("SERVICE_DATE")
    timeout = os.getenv("INVENTORY_TIMEOUT_SECONDS")
    return ToolContext(
        db_path=DB_PATH,
        inventory=InventoryClient(
            inventory_api_url(),
            timeout=float(timeout) if timeout else DEFAULT_INVENTORY_TIMEOUT_SECONDS,
        ),
        service_date=(
            date.fromisoformat(service_date) if service_date else datetime.now(timezone).date()
        ),
        timezone=timezone,
    )
