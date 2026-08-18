from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import EcoserviceApi, EcoserviceApiError, EcoserviceNotFound
from .const import (
    CONF_ADDRESS,
    CONF_CONTAINERS,
    CONF_MUNICIPALITY,
    CONF_VASA_ENABLED,
    CONF_VASA_PASSWORD,
    CONF_VASA_USERNAME,
    DOMAIN,
)
from .models import WASTE_NAMES
from .vasa_api import VasaApi, VasaApiError


class EcoserviceConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.api: EcoserviceApi | None = None
        self._containers = []
        self._schedules = {}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        self.api = self.api or EcoserviceApi(async_get_clientsession(self.hass))
        errors = {}
        try: municipalities = await self.api.municipalities()
        except EcoserviceApiError: municipalities, errors = [], {"base":"cannot_connect"}
        if user_input:
            self.values.update(user_input); return await self.async_step_address()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(CONF_MUNICIPALITY): SelectSelector(SelectSelectorConfig(options=municipalities, mode=SelectSelectorMode.DROPDOWN))}), errors=errors)

    async def async_step_address(self, user_input=None) -> ConfigFlowResult:
        assert self.api
        errors = {}
        if user_input and CONF_ADDRESS in user_input:
            address = user_input[CONF_ADDRESS].strip()
            try:
                addresses = await self.api.addresses(self.values[CONF_MUNICIPALITY], address)
                if address not in addresses: raise EcoserviceNotFound
                self.values[CONF_ADDRESS] = address
                return await self.async_step_containers()
            except EcoserviceNotFound: errors["base"] = "invalid_address"
            except EcoserviceApiError: errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="address", data_schema=vol.Schema({vol.Required(CONF_ADDRESS): TextSelector(TextSelectorConfig(type="text", autocomplete="street-address"))}), errors=errors, description_placeholders={"municipality":self.values[CONF_MUNICIPALITY]})

    async def async_step_containers(self, user_input=None) -> ConfigFlowResult:
        assert self.api
        errors = {}
        try: self._containers = await self.api.containers(self.values[CONF_MUNICIPALITY], self.values[CONF_ADDRESS])
        except EcoserviceApiError: self._containers, errors = [], {"base":"cannot_connect"}
        if not self._containers and not errors: errors["base"] = "container_not_found"
        if user_input:
            selected = user_input[CONF_CONTAINERS]
            try:
                self._schedules = await self.api.schedules(self.values[CONF_MUNICIPALITY], self.values[CONF_ADDRESS], selected)
                self.values[CONF_CONTAINERS] = selected
                return await self.async_step_confirm()
            except EcoserviceNotFound: errors["base"] = "empty_schedule"
            except EcoserviceApiError: errors["base"] = "cannot_connect"
        options = [SelectOptionDict(value=c.inventory_number, label=f"{c.inventory_number} — {WASTE_NAMES[c.waste_type]}" + (f" — {c.capacity}" if c.capacity else "")) for c in self._containers]
        return self.async_show_form(step_id="containers", data_schema=vol.Schema({vol.Required(CONF_CONTAINERS): SelectSelector(SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST))}), errors=errors)

    async def async_step_confirm(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self.values[CONF_VASA_ENABLED] = bool(user_input.get(CONF_VASA_ENABLED))
            if self.values[CONF_VASA_ENABLED]:
                return await self.async_step_vasa()
            return await self._async_finish()
        summary = "; ".join(f"{key}: {WASTE_NAMES[item.container.waste_type]} ({', '.join(d.isoformat() for d in item.dates[:3])})" for key,item in self._schedules.items())
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({vol.Optional(CONF_VASA_ENABLED, default=False): BooleanSelector()}), description_placeholders={"municipality":self.values[CONF_MUNICIPALITY],"address":self.values[CONF_ADDRESS],"summary":summary})

    async def async_step_vasa(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            api = VasaApi(async_get_clientsession(self.hass), user_input[CONF_VASA_USERNAME], user_input[CONF_VASA_PASSWORD])
            try:
                await api.authenticate()
            except VasaApiError:
                errors["base"] = "vasa_auth_failed"
            else:
                self.values.update(user_input)
                return await self._async_finish()
        return self.async_show_form(step_id="vasa", data_schema=vol.Schema({vol.Required(CONF_VASA_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")), vol.Required(CONF_VASA_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password"))}), errors=errors)

    async def _async_finish(self) -> ConfigFlowResult:
        await self.async_set_unique_id(f"{self.values[CONF_MUNICIPALITY]}|{self.values[CONF_ADDRESS]}".casefold())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=self.values[CONF_ADDRESS], data=self.values)

    @staticmethod
    def async_get_options_flow(config_entry): return EcoserviceOptionsFlow(config_entry)


class EcoserviceOptionsFlow(OptionsFlow):
    def __init__(self, entry) -> None: self.entry = entry
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data, **user_input})
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="init", data_schema=vol.Schema({vol.Required(CONF_MUNICIPALITY, default=self.entry.data[CONF_MUNICIPALITY]): str, vol.Required(CONF_ADDRESS, default=self.entry.data[CONF_ADDRESS]): str, vol.Required(CONF_CONTAINERS, default=self.entry.data[CONF_CONTAINERS]): SelectSelector(SelectSelectorConfig(options=self.entry.data[CONF_CONTAINERS], multiple=True, custom_value=True)), vol.Optional(CONF_VASA_ENABLED, default=self.entry.data.get(CONF_VASA_ENABLED, False)): BooleanSelector(), vol.Optional(CONF_VASA_USERNAME, default=self.entry.data.get(CONF_VASA_USERNAME, "")): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")), vol.Optional(CONF_VASA_PASSWORD, default=self.entry.data.get(CONF_VASA_PASSWORD, "")): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password"))}))
