from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CONTAINERS, CONF_VASA_PASSWORD, CONF_VASA_USERNAME, DOMAIN, PLATFORMS
from .coordinator import EcoserviceCoordinator
from .models import WasteType, selected_waste_types
from .vasa_api import VasaApi

type EcoserviceConfigEntry = ConfigEntry[EcoserviceCoordinator]

# Per-waste-type sensors that version 2 created even without a matching container.
LEGACY_WASTE_SENSOR_SLUGS = {WasteType.PAPER: "paper", WasteType.GLASS: "glass", WasteType.MIXED: "mixed_waste"}
LEGACY_WASTE_SENSOR_UNIQUE_IDS = (
    "next_{slug}_collection_date",
    "this_year_{slug}_weight",
    "last_{slug}_weight",
    "last_{slug}_service_status",
    "last_{slug}_collection_date",
)


async def async_migrate_entry(hass: HomeAssistant, entry: EcoserviceConfigEntry) -> bool:
    registry = er.async_get(hass)
    if entry.version < 2:
        legacy_entities = (
            (Platform.BINARY_SENSOR, f"{entry.entry_id}_ecoservice_api_connection"),
            (Platform.SENSOR, f"{entry.entry_id}_last_update_from_ecoservice"),
        )
        for platform, unique_id in legacy_entities:
            if entity_id := registry.async_get_entity_id(platform, DOMAIN, unique_id):
                registry.async_remove(entity_id)
        hass.config_entries.async_update_entry(entry, version=2)
    if entry.version < 3:
        selected_types = selected_waste_types(entry.data[CONF_CONTAINERS])
        for waste_type, slug in LEGACY_WASTE_SENSOR_SLUGS.items():
            if waste_type in selected_types:
                continue
            for template in LEGACY_WASTE_SENSOR_UNIQUE_IDS:
                unique_id = f"{entry.entry_id}_{template.format(slug=slug)}"
                if entity_id := registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id):
                    registry.async_remove(entity_id)
        hass.config_entries.async_update_entry(entry, version=3)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EcoserviceConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    username = entry.data.get(CONF_VASA_USERNAME)
    password = entry.data.get(CONF_VASA_PASSWORD)
    if not username or not password:
        raise ConfigEntryAuthFailed("VASA credentials are required")
    coordinator = EcoserviceCoordinator(hass, entry, VasaApi(session, username, password))
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
