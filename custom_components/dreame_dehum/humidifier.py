"""The dehumidifier itself: power, mode and target humidity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DreameDehumConfigEntry, DreameDehumCoordinator
from .entity import DreameDehumEntity
from .profiles import Kind

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameDehumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the dehumidifier entity."""
    coordinator = entry.runtime_data
    if coordinator.device.profile.prop("power"):
        async_add_entities([DreameDehumidifier(coordinator)])


class DreameDehumidifier(DreameDehumEntity, HumidifierEntity):
    """Power, mode and target humidity in one entity."""

    _attr_name = None
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER

    def __init__(self, coordinator: DreameDehumCoordinator) -> None:
        super().__init__(coordinator, "power")
        self._attr_translation_key = "dehumidifier"
        profile = coordinator.device.profile
        mode = profile.prop("mode")
        self._modes: dict[int, str] = dict(mode.options or {}) if mode and mode.writable else {}
        if self._modes:
            self._attr_supported_features = HumidifierEntityFeature.MODES
            self._attr_available_modes = list(self._modes.values())
        target = profile.prop("target_humidity")
        self._target_writable = bool(target and target.writable)
        if target and target.values:
            self._attr_min_humidity = min(target.values)
            self._attr_max_humidity = max(target.values)
        current = profile.of_kind(Kind.HUMIDITY)
        self._current_key = current[0].key if current else None

    @property
    def is_on(self) -> bool:
        return self.device.is_on(self.data)

    @property
    def mode(self) -> str | None:
        return self._modes.get(self.data.get("mode"))  # type: ignore[arg-type]

    @property
    def target_humidity(self) -> float | None:
        value = self.data.get("target_humidity")
        return value if isinstance(value, (int, float)) else None

    @property
    def current_humidity(self) -> float | None:
        value = self.data.get(self._current_key) if self._current_key else None
        return value if isinstance(value, (int, float)) else None

    @property
    def action(self) -> HumidifierAction | None:
        if not self.is_on:
            return HumidifierAction.OFF
        # The unit doesn't report its compressor state, so this is inferred:
        # below the target, a dehumidifier has nothing to do.
        current, target = self.current_humidity, self.target_humidity
        if current is not None and target is not None and current < target:
            return HumidifierAction.IDLE
        return HumidifierAction.DRYING

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.device.set_power(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.device.set_power(False))

    async def async_set_mode(self, mode: str) -> None:
        value = next(v for v, name in self._modes.items() if name == mode)
        await self.coordinator.async_write("mode", value)

    async def async_set_humidity(self, humidity: int) -> None:
        await self.coordinator.async_write("target_humidity", self.device.snap_humidity(humidity))
