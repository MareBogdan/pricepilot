"""The mock store as seen by the action layer (ADR-0047).

`Store` is a small protocol so tests can substitute a recording fake; `HttpStore` talks to
`services/mock_store` (`uv run uvicorn services.mock_store.app:app --port 8001`). The store keeps its
prices and its `/audit-log` in process memory: a restart resets both, which the action layer treats as
"the store drifted" (rollback refuses), never as something to paper over.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx

DEFAULT_STORE_URL = "http://127.0.0.1:8001"


@dataclass(frozen=True, slots=True)
class StoreWrite:
    """One entry of the store's audit log."""

    product_id: int
    previous_price: Decimal
    new_price: Decimal
    reason: str


class Store(Protocol):
    def get_price(self, product_id: int) -> Decimal: ...

    def set_price(self, product_id: int, price: Decimal, reason: str) -> StoreWrite: ...

    def audit_log(self) -> list[StoreWrite]: ...


def _write(entry: dict[str, Any]) -> StoreWrite:
    # Money crosses HTTP as JSON strings/numbers: always rebuild Decimal from the text, never float.
    return StoreWrite(
        product_id=int(entry["product_id"]),
        previous_price=Decimal(str(entry["previous_price"])),
        new_price=Decimal(str(entry["new_price"])),
        reason=str(entry["reason"]),
    )


class HttpStore:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    @classmethod
    def connect(cls, base_url: str = DEFAULT_STORE_URL, timeout: float = 10.0) -> HttpStore:
        return cls(httpx.Client(base_url=base_url, timeout=timeout))

    def get_price(self, product_id: int) -> Decimal:
        response = self._client.get(f"/products/{product_id}")
        response.raise_for_status()
        return Decimal(str(response.json()["current_price"]))

    def set_price(self, product_id: int, price: Decimal, reason: str) -> StoreWrite:
        response = self._client.patch(
            f"/products/{product_id}/price", json={"price": str(price), "reason": reason}
        )
        response.raise_for_status()
        return _write(response.json())

    def audit_log(self) -> list[StoreWrite]:
        response = self._client.get("/audit-log")
        response.raise_for_status()
        return [_write(e) for e in response.json()]
