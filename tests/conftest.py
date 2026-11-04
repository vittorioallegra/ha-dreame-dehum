"""Shared fixtures: a fake Dreame cloud that records every command."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dreame_dehum.const import CONF_DID, CONF_HOST, CONF_MAC, CONF_MODEL, CONF_REGION, DOMAIN

DID = "123456789"
DD20_MODEL = "dreame.dehum.u2512"
HOST = "10000.mt.eu.iot.dreame.tech:19973"

# A plausible DD20, on, in Custom mode. Values follow the shapes seen on a real
# unit; the identifiers are made up.
DD20_VALUES: dict[tuple[int, int], Any] = {
    (1, 5): "TESTSERIAL0000001",
    (2, 1): 1,
    (2, 2): 0,
    (2, 3): 3,
    (2, 4): 0,
    (2, 5): 55,
    (2, 6): 0,
    (2, 7): 0,
    (2, 10): 0,
    (3, 2): 70,
    (3, 3): 20,
    (4, 1): 1,
    (5, 1): 0,
    (6, 4): 0,
    (7, 1): 0,
    (7, 2): 0,
    (7, 4): 0,
    (7, 5): 0,
    (7, 6): 1,
    (7, 7): 1,
    (7, 8): 2400,
}


def device_record(model: str = DD20_MODEL, did: str = DID, name: str = "Test Dehumidifier") -> dict[str, Any]:
    return {
        "did": did,
        "model": model,
        "customName": name,
        "bindDomain": HOST,
        "mac": "AA:BB:CC:DD:EE:FF",
        "ver": "1.0.0_0001",
    }


class FakeCloud:
    """Stands in for DreameCloud."""

    def __init__(self) -> None:
        self.devices: list[dict[str, Any]] = [device_record()]
        self.values: dict[tuple[int, int], Any] = dict(DD20_VALUES)
        self.calls: list[tuple[Any, ...]] = []
        self.login_error: Exception | None = None
        self.read_error: Exception | None = None
        self.write_error: Exception | None = None

    async def login(self) -> None:
        if self.login_error:
            raise self.login_error

    async def get_devices(self) -> list[dict[str, Any]]:
        await self.login()
        return self.devices

    async def get_properties(
        self, did: str, host: str | None, addresses: list[tuple[int, int]]
    ) -> dict[tuple[int, int], Any]:
        if self.read_error:
            raise self.read_error
        self.calls.append(("get", tuple(addresses)))
        return {a: self.values[a] for a in addresses if a in self.values}

    async def set_property(self, did: str, host: str | None, siid: int, piid: int, value: Any) -> None:
        if self.write_error:
            raise self.write_error
        self.calls.append(("set", siid, piid, value))
        self.values[(siid, piid)] = value

    async def call_action(self, did: str, host: str | None, siid: int, aiid: int) -> None:
        self.calls.append(("action", siid, aiid))

    @property
    def writes(self) -> list[tuple[Any, ...]]:
        return [c for c in self.calls if c[0] != "get"]

    @property
    def addresses_read(self) -> set[tuple[int, int]]:
        return {a for c in self.calls if c[0] == "get" for a in c[1]}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/dreame_dehum."""


@pytest.fixture
def cloud() -> Iterator[FakeCloud]:
    fake = FakeCloud()
    with (
        patch("custom_components.dreame_dehum.DreameCloud", return_value=fake),
        patch("custom_components.dreame_dehum.config_flow.DreameCloud", return_value=fake),
    ):
        yield fake


def make_entry(model: str = DD20_MODEL, options: dict[str, Any] | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Dehumidifier",
        unique_id=DID,
        data={
            "username": "user@example.com",
            "password": "not-a-real-password",
            CONF_REGION: "eu",
            CONF_DID: DID,
            CONF_MODEL: model,
            CONF_HOST: HOST,
            CONF_MAC: "AA:BB:CC:DD:EE:FF",
        },
        options=options or {},
    )
