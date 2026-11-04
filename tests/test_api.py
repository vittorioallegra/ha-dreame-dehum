"""The cloud client's handling of replies."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from custom_components.dreame_dehum.api import DreameCloud


async def test_missing_addresses_are_dropped() -> None:
    cloud = DreameCloud(None, "user@example.com", "x", "eu")  # type: ignore[arg-type]
    reply: list[dict[str, Any]] = [
        {"siid": 2, "piid": 1, "code": 0, "value": 1},
        {"siid": 2, "piid": 8, "code": 0, "value": -4001},  # no such property
        {"siid": 8, "piid": 1, "code": 0, "value": -4005},  # no such service
        {"siid": 3, "piid": 2, "code": 0, "value": None},
        {"siid": 3, "piid": 3, "code": -1, "value": 20},
    ]
    cloud._command = AsyncMock(return_value=reply)  # type: ignore[method-assign]
    values = await cloud.get_properties("1", None, [(2, 1), (2, 8), (8, 1), (3, 2), (3, 3)])
    assert values == {(2, 1): 1}
