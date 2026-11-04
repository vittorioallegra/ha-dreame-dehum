"""Config flow for Dreame Dehumidifier."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import AuthFailed, DreameCloud, DreameError
from .const import (
    CONF_DID,
    CONF_HOST,
    CONF_MAC,
    CONF_MODEL,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGIONS,
)
from .profiles import get_profile

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): _PASSWORD,
        vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
            SelectSelectorConfig(options=REGIONS, translation_key="region")
        ),
    }
)


def _is_dehumidifier(device: dict[str, Any]) -> bool:
    return ".dehum." in str(device.get("model", ""))


def _device_name(device: dict[str, Any]) -> str:
    info = device.get("deviceInfo") or {}
    return device.get("customName") or info.get("displayName") or "Dreame Dehumidifier"


def _device_label(device: dict[str, Any]) -> str:
    model = str(device.get("model", ""))
    profile = get_profile(model)
    detail = profile.name if profile else f"{model}, not supported yet"
    return f"{_device_name(device)} ({detail})"


class DreameDehumConfigFlow(ConfigFlow, domain=DOMAIN):
    """Sign in, then pick a dehumidifier."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._devices: dict[str, dict[str, Any]] = {}

    async def _fetch_devices(self, user_input: dict[str, Any]) -> list[dict[str, Any]]:
        cloud = DreameCloud(
            async_get_clientsession(self.hass),
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            user_input[CONF_REGION],
        )
        await cloud.login()
        return await cloud.get_devices()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the Dreamehome account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                devices = await self._fetch_devices(user_input)
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except DreameError:
                errors["base"] = "cannot_connect"
            else:
                configured = {entry.unique_id for entry in self._async_current_entries()}
                self._devices = {
                    str(d["did"]): d for d in devices if _is_dehumidifier(d) and str(d["did"]) not in configured
                }
                if not self._devices:
                    return self.async_abort(reason="no_devices")
                self._credentials = user_input
                return await self.async_step_device()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick which dehumidifier to add."""
        if user_input is None and len(self._devices) > 1:
            options = [SelectOptionDict(value=did, label=_device_label(d)) for did, d in self._devices.items()]
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema({vol.Required(CONF_DID): SelectSelector(SelectSelectorConfig(options=options))}),
            )
        did = user_input[CONF_DID] if user_input else next(iter(self._devices))
        device = self._devices[did]
        await self.async_set_unique_id(did)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=_device_name(device),
            data={
                **self._credentials,
                CONF_DID: did,
                CONF_MODEL: device.get("model"),
                CONF_HOST: device.get("bindDomain"),
                CONF_MAC: device.get("mac"),
            },
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The account was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the password again."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await self._fetch_devices(credentials)
            except AuthFailed:
                errors["base"] = "invalid_auth"
            except DreameError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> DreameDehumOptionsFlow:
        """Return the options flow."""
        return DreameDehumOptionsFlow()


class DreameDehumOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(data={**user_input, CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])})
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
