"""On/off settings: child lock, plasma, swing."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DreameDehumConfigEntry, DreameDehumCoordinator
from .entity import DreameDehumEntity
from .profiles import Kind

PARALLEL_UPDATES = 1

# Settings that change what the unit does rather than how it is configured.
_MAIN = {"plasma", "swing", "air_drying"}


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameDehumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a switch for each writable on/off property."""
    coordinator = entry.runtime_data
    async_add_entities(
        DreameDehumSwitch(coordinator, prop.key) for prop in coordinator.device.profile.of_kind(Kind.SWITCH)
    )


class DreameDehumSwitch(DreameDehumEntity, SwitchEntity):
    """One on/off setting."""

    def __init__(self, coordinator: DreameDehumCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        if key not in _MAIN:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return bool(self.raw_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._key == "air_drying":
            await self.coordinator.async_command(self.device.set_air_drying(self.data, True))
        else:
            await self.coordinator.async_write(self._key, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._key == "air_drying":
            await self.coordinator.async_command(self.device.set_air_drying(self.data, False))
        else:
            await self.coordinator.async_write(self._key, 0)
