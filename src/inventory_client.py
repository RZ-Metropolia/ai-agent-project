"""Client for the inventory API. Any failure becomes InventoryUnavailable, never a stock value."""

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class InventoryUnavailable(Exception):
    """Stock could not be read, so nothing may be assumed about it."""


class _InventoryRow(BaseModel):
    model_config = ConfigDict(strict=True)

    item_id: int
    portions: int = Field(ge=0)


class _InventoryResponse(BaseModel):
    items: list[_InventoryRow]


class InventoryClient:
    def __init__(self, base_url, timeout=2.0, transport=None):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    def get_portions(self):
        """Return {item_id: portions left} from the API, or raise InventoryUnavailable."""
        try:
            # trust_env=False keeps a system proxy from intercepting the local mock API.
            with httpx.Client(
                timeout=self._timeout, transport=self._transport, trust_env=False
            ) as client:
                response = client.get(f"{self._base_url}/inventory")
            response.raise_for_status()
            rows = _InventoryResponse.model_validate_json(response.content).items
        except httpx.TimeoutException as exc:
            raise InventoryUnavailable("the inventory service timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise InventoryUnavailable(
                f"the inventory service returned HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise InventoryUnavailable("the inventory service could not be reached") from exc
        except ValidationError as exc:
            raise InventoryUnavailable("the inventory service returned invalid data") from exc

        portions = {row.item_id: row.portions for row in rows}
        if len(portions) != len(rows):
            raise InventoryUnavailable("the inventory service returned duplicate items")
        return portions


def set_inventory_mode(base_url, mode):
    """Switch the mock API's mode, for tests and the evaluation runner."""
    with httpx.Client(trust_env=False) as client:
        response = client.post(f"{base_url.rstrip('/')}/_admin/mode", json={"mode": mode})
    response.raise_for_status()
