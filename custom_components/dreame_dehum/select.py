"""Settings with named options: the fan speed."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DreameDehumConfigEntry, DreameDehumCoordinator
from .entity import DreameDehumEntity
from .profiles import Kind

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameDehumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a select for each writable property with named options."""
    coordinator = entry.runtime_data
    async_add_entities(
        DreameDehumSelect(coordinator, prop.key)
        for prop in coordinator.device.profile.of_kind(Kind.SELECT)
        if prop.writable and prop.options
    )


class DreameDehumSelect(DreameDehumEntity, SelectEntity):
    """One setting with named options."""

    def __init__(self, coordinator: DreameDehumCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._values = dict(coordinator.device.profile.prop(key).options or {})  # type: ignore[union-attr]
        self._attr_options = list(self._values.values())

    @property
    def current_option(self) -> str | None:
        return self._values.get(self.raw_value)  # type: ignore[arg-type]

    async def async_select_option(self, option: str) -> None:
        value = next(v for v, name in self._values.items() if name == option)
        if self._key == "fan_speed":
            # The fan speed can only be set in the manual mode; switch to it first.
            await self.coordinator.async_command(self.device.set_fan_speed(self.data, value))
        else:
            await self.coordinator.async_write(self._key, value)
