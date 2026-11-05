"""The timer."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DreameDehumConfigEntry, DreameDehumCoordinator
from .entity import DreameDehumEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameDehumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the timer if the profile can set it."""
    coordinator = entry.runtime_data
    prop = coordinator.device.profile.prop("timer_hours")
    if prop and prop.writable:
        async_add_entities([DreameDehumTimer(coordinator)])


class DreameDehumTimer(DreameDehumEntity, NumberEntity):
    """Hours until the dehumidifier switches itself off; 0 means no timer."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: DreameDehumCoordinator) -> None:
        super().__init__(coordinator, "timer_hours")
        values = coordinator.device.profile.prop("timer_hours").values  # type: ignore[union-attr]
        self._attr_native_min_value = 0
        self._attr_native_max_value = max(values)  # type: ignore[arg-type]

    @property
    def available(self) -> bool:
        # The unit may leave the hours out while no timer runs; that means 0.
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float:
        value = self.raw_value
        return value if isinstance(value, (int, float)) else 0

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(self.device.set_timer(int(value)))
