"""Room readings, the self-drying countdown and raw diagnostics."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DreameDehumConfigEntry, DreameDehumCoordinator
from .entity import DreameDehumEntity
from .profiles import Kind

PARALLEL_UPDATES = 0

_M = SensorStateClass.MEASUREMENT
_D = EntityCategory.DIAGNOSTIC

DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    d.key: d
    for d in (
        SensorEntityDescription(
            key="humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=_M,
        ),
        SensorEntityDescription(
            key="temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=_M,
        ),
        SensorEntityDescription(
            key="air_dry_remaining",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        SensorEntityDescription(
            key="air_dry_duration",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.MINUTES,
            entity_category=_D,
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameDehumConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a sensor for each reading, plus a disabled raw sensor for each unmapped property."""
    coordinator = entry.runtime_data
    profile = coordinator.device.profile
    entities: list[SensorEntity] = []
    for prop in profile.props:
        if prop.kind in (Kind.SENSOR, Kind.HUMIDITY):
            entities.append(
                DreameDehumSensor(coordinator, DESCRIPTIONS.get(prop.key) or SensorEntityDescription(key=prop.key))
            )
        elif prop.kind is Kind.UNKNOWN:
            entities.append(DreameDehumRawSensor(coordinator, prop.key, f"{prop.siid}/{prop.piid}"))
    async_add_entities(entities)


class DreameDehumSensor(DreameDehumEntity, SensorEntity):
    """One numeric reading."""

    def __init__(self, coordinator: DreameDehumCoordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        value = self.raw_value
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class DreameDehumRawSensor(DreameDehumEntity, SensorEntity):
    """A property whose meaning isn't known yet, shown as its raw value.

    Disabled by default. Enabling it helps map the property: watch how it
    changes while using the unit, then report it.
    """

    _attr_entity_category = _D
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: DreameDehumCoordinator, key: str, address: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = "unknown_property"
        self._attr_translation_placeholders = {"address": address}

    @property
    def native_value(self) -> str | int | float | None:
        value = self.raw_value
        return value if isinstance(value, (str, int, float)) else None
