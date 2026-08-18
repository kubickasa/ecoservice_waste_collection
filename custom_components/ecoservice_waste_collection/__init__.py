from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EcoserviceApi
from .const import CONF_VASA_ENABLED, CONF_VASA_PASSWORD, CONF_VASA_USERNAME, PLATFORMS
from .coordinator import EcoserviceCoordinator
from .vasa_api import VasaApi

type EcoserviceConfigEntry = ConfigEntry[EcoserviceCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EcoserviceConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    vasa_api = VasaApi(session, entry.data[CONF_VASA_USERNAME], entry.data[CONF_VASA_PASSWORD]) if entry.data.get(CONF_VASA_ENABLED) else None
    coordinator = EcoserviceCoordinator(hass, entry, EcoserviceApi(session), vasa_api)
    await coordinator.async_load_cached()
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        if coordinator.data is None:
            raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [Platform(item) for item in PLATFORMS])
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: EcoserviceConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EcoserviceConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, [Platform(item) for item in PLATFORMS])
