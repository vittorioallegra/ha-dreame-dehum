"""One dehumidifier, seen through its profile.

Every read and write goes through here, and anything the profile doesn't
declare is refused before it reaches the cloud. Entities never talk to
DreameCloud directly.
"""

from __future__ import annotations

from typing import Any

from .api import DreameCloud
from .const import READ_BATCH_SIZE
from .profiles import Profile


class NotAllowed(Exception):
    """The profile doesn't allow this command."""


class DreameDevice:
    """Guarded access to one device."""

    def __init__(self, cloud: DreameCloud, profile: Profile, did: str, host: str | None) -> None:
        self.cloud = cloud
        self.profile = profile
        self.did = did
        self.host = host

    async def read_all(self) -> dict[str, Any]:
        """Read every property in the profile, keyed by property key."""
        props = self.profile.props
        raw: dict[tuple[int, int], Any] = {}
        for start in range(0, len(props), READ_BATCH_SIZE):
            batch = [p.address for p in props[start : start + READ_BATCH_SIZE]]
            raw.update(await self.cloud.get_properties(self.did, self.host, batch))
        return {p.key: raw[p.address] for p in props if p.address in raw}

    async def write(self, key: str, value: int) -> None:
        """Write a property, if the profile allows that value."""
        prop = self.profile.prop(key)
        if prop is None or not prop.writable:
            raise NotAllowed(f"{self.profile.name}: {key} can't be written")
        if value not in prop.values:  # type: ignore[operator]
            raise NotAllowed(f"{self.profile.name}: {value} isn't an allowed value for {key}")
        await self.cloud.set_property(self.did, self.host, prop.siid, prop.piid, value)

    # --- dehumidifier operations -------------------------------------------

    def is_on(self, data: dict[str, Any]) -> bool:
        return data.get("power") == self.profile.power_on

    async def set_power(self, on: bool) -> dict[str, Any]:
        value = self.profile.power_on if on else self.profile.power_off
        await self.write("power", value)
        return {"power": value}

    async def set_fan_speed(self, data: dict[str, Any], speed: int) -> dict[str, Any]:
        """Set the fan speed, switching to the manual mode first when needed."""
        written: dict[str, Any] = {}
        manual = self.profile.manual_mode
        if manual is not None and data.get("mode") != manual:
            await self.write("mode", manual)
            written["mode"] = manual
        await self.write("fan_speed", speed)
        written["fan_speed"] = speed
        return written

    def snap_humidity(self, humidity: float) -> int:
        """Round a target humidity to the nearest value the model accepts."""
        values = sorted(self.profile.prop("target_humidity").values or ())  # type: ignore[union-attr]
        return min(values, key=lambda v: abs(v - humidity))
