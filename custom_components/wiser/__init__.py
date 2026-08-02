"""Drayton Wiser Compoment for Wiser System.

https://github.com/asantaga/wiserHomeAssistantPlatform
msparker@sky.com
"""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from .const import (
    CONF_AUTOMATIONS_HW_AUTO_MODE,
    CONF_AUTOMATIONS_HW_CLIMATE,
    CONF_AUTOMATIONS_HW_HEAT_MODE,
    CONF_AUTOMATIONS_HW_SENSOR_ENTITY_ID,
    CONF_AUTOMATIONS_PASSIVE,
    CONF_AUTOMATIONS_PASSIVE_TEMP_INCREMENT,
    CONF_DEPRECATED_HW_TARGET_TEMP,
    CONF_ENABLE_HEATING_ENTITIES,
    CONF_GROUP_LIGHTS_WITH_ROOM,
    DATA,
    DEFAULT_ENABLE_HEATING_ENTITIES,
    DEFAULT_GROUP_LIGHTS_WITH_ROOM,
    DOMAIN,
    MANUFACTURER,
    UPDATE_LISTENER,
    WISER_PLATFORMS,
    WISER_SERVICES,
    HWCycleModes,
)
from .coordinator import WiserUpdateCoordinator
from .frontend import JSModuleRegistration
from .helpers import get_device_name, get_identifier, get_instance_count
from .services import async_setup_services
from .websockets import async_register_websockets

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version == 1:
        new_options = {**config_entry.options}
        if config_entry.minor_version < 3:
            # move passive mode options into new section
            if new_options.get(CONF_AUTOMATIONS_PASSIVE) is not None:
                # detect if failed last upgrade to minor version 2
                if isinstance(new_options.get(CONF_AUTOMATIONS_PASSIVE), bool):
                    new_options[CONF_AUTOMATIONS_PASSIVE] = {
                        CONF_AUTOMATIONS_PASSIVE: new_options[CONF_AUTOMATIONS_PASSIVE]
                    }
                    for item in [
                        CONF_AUTOMATIONS_PASSIVE_TEMP_INCREMENT,
                    ]:
                        if new_options.get(item):
                            new_options[CONF_AUTOMATIONS_PASSIVE][item] = new_options[
                                item
                            ]
                            del new_options[item]

            # hw climate
            if new_options.get(CONF_AUTOMATIONS_HW_CLIMATE) is not None:
                # detect if failed last upgrade to minor version 2
                if isinstance(new_options.get(CONF_AUTOMATIONS_HW_CLIMATE), bool):
                    if new_options.get(CONF_DEPRECATED_HW_TARGET_TEMP):
                        del new_options[CONF_DEPRECATED_HW_TARGET_TEMP]

                    new_options[CONF_AUTOMATIONS_HW_CLIMATE] = {
                        CONF_AUTOMATIONS_HW_CLIMATE: new_options[
                            CONF_AUTOMATIONS_HW_CLIMATE
                        ]
                    }
                    for item in [
                        CONF_AUTOMATIONS_HW_AUTO_MODE,
                        CONF_AUTOMATIONS_HW_HEAT_MODE,
                        CONF_AUTOMATIONS_HW_SENSOR_ENTITY_ID,
                    ]:
                        if value := new_options.get(item):
                            if value == "Normal":
                                value = HWCycleModes.CONTINUOUS
                            if value == "Override":
                                value = HWCycleModes.ONCE
                            new_options[CONF_AUTOMATIONS_HW_CLIMATE][item] = value
                            del new_options[item]

        hass.config_entries.async_update_entry(
            config_entry, options=new_options, minor_version=3, version=1
        )

    _LOGGER.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry):
    """Set up Wiser from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = WiserUpdateCoordinator(hass, config_entry)

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_status == "Success":
        raise ConfigEntryNotReady

    # Update listener for config option changes
    update_listener = config_entry.add_update_listener(_async_update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = {
        DATA: coordinator,
        UPDATE_LISTENER: update_listener,
    }

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(config_entry, WISER_PLATFORMS)

    # Cleanup orphaned devices based on options
    await async_cleanup_devices(hass, config_entry, coordinator)

    # Setup websocket services for frontend cards
    await async_register_websockets(hass, coordinator)

    # Setup services
    await async_setup_services(hass, coordinator)

    # Add hub as device
    await async_update_device_registry(hass, config_entry)

    # Register custom cards
    moodule_register = JSModuleRegistration(hass)
    await moodule_register.async_register()

    _LOGGER.info(
        "Wiser Component Setup Completed (%s)", coordinator.wiserhub.system.name
    )
    return True


async def async_update_device_registry(hass: HomeAssistant, config_entry):
    """Update device registry."""
    data = hass.data[DOMAIN][config_entry.entry_id][DATA]
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={
            (CONNECTION_NETWORK_MAC, data.wiserhub.system.network.mac_address)
        },
        identifiers={(DOMAIN, data.wiserhub.system.name)},
        manufacturer=MANUFACTURER,
        name=get_device_name(data, 0),
        model=data.wiserhub.system.model,
        sw_version=data.wiserhub.system.firmware_version,
    )


async def async_cleanup_devices(hass: HomeAssistant, config_entry, coordinator):
    """Remove devices and entities that should no longer exist based on current options."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    # Get all devices for this config entry
    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)

    for device in devices:
        # Skip the hub device
        if device.model == "Controller":
            continue

        should_remove = False

        # If heating is disabled, remove Room devices (but keep them if lights are grouped with room)
        if (
            not coordinator.enable_heating_entities
            and device.model == "Room"
            and not coordinator.group_lights_with_room
        ):
            _LOGGER.debug(f"Removing room device: {device.name} (heating disabled)")
            should_remove = True

        # If group_by_room is enabled, remove separate device cards
        # (entities will be re-created under the room device)
        if coordinator.group_lights_with_room and not should_remove:
            entities = er.async_entries_for_device(
                entity_registry, device.id, include_disabled_entities=True
            )
            # Any device with entities that has a non-Room/Controller model should be removed
            if entities and device.model not in ("Room", "Controller"):
                _LOGGER.debug(f"Removing device: {device.name} (grouped with room)")
                should_remove = True

        if should_remove:
            # Remove all entities for this device first
            entities = er.async_entries_for_device(
                entity_registry, device.id, include_disabled_entities=True
            )
            for entity in entities:
                entity_registry.async_remove(entity.entity_id)
            device_registry.async_remove_device(device.id)

    # Also remove orphaned entities that are no longer created
    # (entities belonging to this config entry with no matching platform)
    if not coordinator.enable_heating_entities:
        all_entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
        heating_prefixes = (
            "climate.", "sensor.wiser_lts_heating", "sensor.wiser_lts_target_temperature",
            "sensor.wiser_lts_temperature", "sensor.wiser_heating",
        )
        for entity in all_entities:
            if entity.entity_id.startswith(heating_prefixes):
                _LOGGER.debug(f"Removing orphaned heating entity: {entity.entity_id}")
                entity_registry.async_remove(entity.entity_id)

    # Remove orphaned moment entities (moments deleted from hub)
    all_entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    active_moment_ids = set()
    if coordinator.wiserhub.moments:
        for moment in coordinator.wiserhub.moments.all:
            active_moment_ids.add(moment.id)
    for entity in all_entities:
        if entity.unique_id and "moment_" in entity.unique_id:
            # Extract moment_id from unique_id like "SystemName-sensor-moment_123-0"
            try:
                part = entity.unique_id.split("moment_")[1].split("-")[0]
                moment_id = int(part)
                if moment_id not in active_moment_ids:
                    _LOGGER.debug(f"Removing orphaned moment entity: {entity.entity_id}")
                    entity_registry.async_remove(entity.entity_id)
            except (ValueError, IndexError):
                pass

    # Remove devices that have no entities (orphaned by rename or option change)
    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    for device in devices:
        if device.model == "Controller":
            continue
        entities = er.async_entries_for_device(
            entity_registry, device.id, include_disabled_entities=True
        )
        if not entities:
            _LOGGER.debug(f"Removing empty device: {device.name}")
            device_registry.async_remove_device(device.id)


async def _async_update_listener(hass: HomeAssistant, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry, device_entry
) -> bool:
    """Delete device if not entities."""
    if device_entry.model == "Controller":
        _LOGGER.error(
            "You cannot delete the Wiser Controller using device delete.  Please remove the integration instead"
        )
        return False
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id][DATA]

    if get_instance_count(hass) == 0:
        # Unload lovelace module resource if only instance
        _LOGGER.debug("Remove Wiser Lovelace cards")
        module_register = JSModuleRegistration(hass)
        await module_register.async_unregister()

        # Deregister services if only instance
        _LOGGER.debug("Unregister Wiser services")
        for service in WISER_SERVICES.values():
            if not data.wiserhub.hotwater and service == "boost_hotwater":
                continue
            hass.services.async_remove(DOMAIN, service)

    _LOGGER.debug("Unload Wiser integration platforms")
    # Unload a config entry
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, platform)
                for platform in WISER_PLATFORMS
            ]
        )
    )

    _LOGGER.debug("Detach config update listener")
    hass.data[DOMAIN][config_entry.entry_id][UPDATE_LISTENER]()

    _LOGGER.debug("Unload integration")
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
