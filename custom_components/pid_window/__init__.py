"""PID Window Controller integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, DEFAULT_KD, DEFAULT_KI, DEFAULT_KP
from .controller import PidWindowController

PLATFORMS = ["switch", "number", "sensor", "button", "select", "text"]


@dataclass
class RuntimeData:
    controller: PidWindowController


_OLD_ENTITY_UNIQUE_IDS = (
    "winter_kp",
    "winter_ki",
    "winter_kd",
    "summer_kp",
    "summer_ki",
    "summer_kd",
    "active_profile",
    "error",
    "temperature_trend",
    "profile_mode",
    "enabled",
    "temp_sensor_guard",
    "outdoor_lock_enabled",
    "outdoor_summer_limit",
    "outdoor_lock_threshold",
)

_OLD_OPTION_KEYS = (
    "profile_mode",
    "winter_kp",
    "winter_ki",
    "winter_kd",
    "summer_kp",
    "summer_ki",
    "summer_kd",
    "outdoor_summer_limit",
    "outdoor_lock_threshold",
    "enable_outdoor_lock",
    "enable_temp_sensor_guard",
    "enabled",
)


def _migrate_pid_options(values: dict, *, fill_defaults: bool = False) -> dict:
    migrated = dict(values)
    if "kp" not in migrated and (fill_defaults or "winter_kp" in values):
        migrated["kp"] = values.get("winter_kp", DEFAULT_KP)
    if "ki" not in migrated and (fill_defaults or "winter_ki" in values):
        migrated["ki"] = values.get("winter_ki", DEFAULT_KI)
    if "kd" not in migrated and (fill_defaults or "winter_kd" in values):
        migrated["kd"] = values.get("winter_kd", DEFAULT_KD)

    if migrated.get("cooling_mode") not in {"disabled", "force", "auto"}:
        if fill_defaults or "cooling_mode" in migrated or "profile_mode" in values:
            migrated["cooling_mode"] = "auto"

    for key in _OLD_OPTION_KEYS:
        migrated.pop(key, None)
    return migrated


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old profile-based PID settings and remove deprecated entities."""
    data = _migrate_pid_options(entry.data, fill_defaults=True)
    options = _migrate_pid_options(entry.options)
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=3)

    registry = er.async_get(hass)
    for old_key in _OLD_ENTITY_UNIQUE_IDS:
        entity_id = registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_{old_key}")
        if entity_id is None:
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{old_key}")
        if entity_id is None:
            entity_id = registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_{old_key}")
        if entity_id is not None:
            registry.async_remove(entity_id)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller = PidWindowController(hass, entry)
    await controller.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = RuntimeData(controller=controller)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: RuntimeData = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime.controller.async_stop()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok
