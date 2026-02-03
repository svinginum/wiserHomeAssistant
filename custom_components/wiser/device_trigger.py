"""Provides device automations for Wiser."""
import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.helpers import config_validation as cv, entity_registry
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .events import WISER_EVENTS, WISER_EVENT, WISER_BUTTON_PANEL_EVENT

DEVICE = "device"
SUPPORTED_DOMAINS = {event[CONF_DOMAIN] for event in WISER_EVENTS}

TRIGGER_TYPES = {event[CONF_TYPE] for event in WISER_EVENTS}
WISER_BUTTON_PANEL_TRIGGER_TYPES = [
    "button_1_pressed",
    "button_2_pressed",
    "button_3_pressed",
    "button_4_pressed",
    "button_1_long_pressed",
    "button_2_long_pressed",
    "button_3_long_pressed",
    "button_4_long_pressed",
]
TRIGGER_TYPES = TRIGGER_TYPES | set(WISER_BUTTON_PANEL_TRIGGER_TYPES)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device triggers for Climate and Button Panel devices."""
    registry = entity_registry.async_get(hass)
    triggers = []

    for entry in entity_registry.async_entries_for_device(registry, device_id):
        if entry.domain in SUPPORTED_DOMAINS:
            trigger_types = set(
                [
                    event_type[CONF_TYPE]
                    for event_type in WISER_EVENTS
                    if event_type[CONF_DOMAIN] == entry.domain
                ]
            )
            triggers.extend(
                [
                    {
                        CONF_PLATFORM: DEVICE,
                        CONF_DEVICE_ID: device_id,
                        CONF_DOMAIN: DOMAIN,
                        CONF_ENTITY_ID: entry.entity_id,
                        CONF_TYPE: trigger_type,
                    }
                    for trigger_type in trigger_types
                ]
            )
        if entry.domain == "sensor" and entry.unique_id and "button_panel_last_button" in entry.unique_id:
            triggers.extend(
                [
                    {
                        CONF_PLATFORM: DEVICE,
                        CONF_DEVICE_ID: device_id,
                        CONF_DOMAIN: DOMAIN,
                        CONF_ENTITY_ID: entry.entity_id,
                        CONF_TYPE: trigger_type,
                    }
                    for trigger_type in WISER_BUTTON_PANEL_TRIGGER_TYPES
                ]
            )

    return triggers


def _button_panel_trigger_params(trigger_type: str) -> tuple[int | None, str | None]:
    """Return (button_number 1-4, press_type 'short'|'long') from trigger type, or (None, None)."""
    if trigger_type not in WISER_BUTTON_PANEL_TRIGGER_TYPES:
        return None, None
    try:
        # button_1_pressed -> 1 short, button_1_long_pressed -> 1 long
        parts = trigger_type.replace("button_", "").replace("_pressed", "").split("_")
        num = int(parts[0]) if parts else None
        press = "long" if (len(parts) > 1 and parts[1] == "long") else "short"
        if num is not None and 1 <= num <= 4:
            return num, press
    except (ValueError, IndexError):
        pass
    return None, None


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    trigger_type = config.get(CONF_TYPE)
    button_number, press_type = _button_panel_trigger_params(trigger_type)

    if button_number is not None and press_type is not None:
        event_data = {
            CONF_ENTITY_ID: config[CONF_ENTITY_ID],
            "button_number": button_number,
            "press_type": press_type,
        }
        event_config = event_trigger.TRIGGER_SCHEMA(
            {
                event_trigger.CONF_PLATFORM: "event",
                event_trigger.CONF_EVENT_TYPE: WISER_BUTTON_PANEL_EVENT,
                event_trigger.CONF_EVENT_DATA: event_data,
            }
        )
        return await event_trigger.async_attach_trigger(
            hass, event_config, action, trigger_info, platform_type="device"
        )

    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: WISER_EVENT,
            event_trigger.CONF_EVENT_DATA: {
                CONF_ENTITY_ID: config[CONF_ENTITY_ID],
                CONF_TYPE: config[CONF_TYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
