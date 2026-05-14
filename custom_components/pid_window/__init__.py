"""PID Window Controller integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, DEFAULT_KD, DEFAULT_KI, DEFAULT_KP
from .controller import PidWindowController

PLATFORMS = ["number", "sensor", "select"]


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
    "temp_deadband_enabled",
    "outdoor_lock_enabled",
    "outdoor_summer_limit",
    "outdoor_lock_threshold",
    "adaptive_outdoor_factor",
    "adaptive_rate_factor",
    "autotune_sample_seconds",
    "calibration_points",
    "autotune",
)

_ENTITY_CATEGORY_BY_UNIQUE_KEY = {
    "target_temp": None,
    "cooling_mode": None,
    "current_temp": None,
    "outdoor_temp": None,
    "error": None,
    "cover_position": None,
    "status": None,
    "temp_deadband": EntityCategory.CONFIG,
    "cooling_delta_threshold": EntityCategory.CONFIG,
    "cooling_delta_hysteresis": EntityCategory.CONFIG,
    "position_change_threshold": EntityCategory.CONFIG,
    "kp": EntityCategory.CONFIG,
    "ki": EntityCategory.CONFIG,
    "kd": EntityCategory.CONFIG,
    "update_interval": EntityCategory.CONFIG,
    "cooling_delta": EntityCategory.DIAGNOSTIC,
    "pid_output": EntityCategory.DIAGNOSTIC,
}

_ENTITY_DOMAIN_BY_UNIQUE_KEY = {
    "target_temp": "number",
    "temp_deadband": "number",
    "cooling_delta_threshold": "number",
    "cooling_delta_hysteresis": "number",
    "position_change_threshold": "number",
    "kp": "number",
    "ki": "number",
    "kd": "number",
    "update_interval": "number",
    "cooling_mode": "select",
    "status": "sensor",
    "cooling_delta": "sensor",
    "error": "sensor",
    "current_temp": "sensor",
    "outdoor_temp": "sensor",
    "cover_position": "sensor",
    "pid_output": "sensor",
}

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
    "adaptive_outdoor_factor",
    "adaptive_rate_factor",
    "autotune_sample_seconds",
    "calibration_points",
    "autotune_step",
)


def _migrate_pid_options(values: dict, *, fill_defaults: bool = False) -> dict:
    migrated = dict(values)
    if "kp" not in migrated and (fill_defaults or "winter_kp" in values):
        migrated["kp"] = values.get("winter_kp", DEFAULT_KP)
    if "ki" not in migrated and (fill_defaults or "winter_ki" in values):
        migrated["ki"] = values.get("winter_ki", DEFAULT_KI)
    if "kd" not in migrated and (fill_defaults or "winter_kd" in values):
        migrated["kd"] = values.get("winter_kd", DEFAULT_KD)

    # v5 changed PID semantics to node-red-contrib-pid style:
    # kp = proportional band, ki = integral time seconds, kd = derivative time seconds.
    # Previous tiny ki/kd gain values are not meaningful as seconds.
    try:
        old_ki = float(migrated.get("ki", DEFAULT_KI))
        if 0 < old_ki < 10:
            migrated["ki"] = DEFAULT_KI
    except (TypeError, ValueError):
        migrated["ki"] = DEFAULT_KI
    try:
        old_kd = float(migrated.get("kd", DEFAULT_KD))
        if 0 < old_kd < 10:
            migrated["kd"] = DEFAULT_KD
    except (TypeError, ValueError):
        migrated["kd"] = DEFAULT_KD

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
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=7)

    registry = er.async_get(hass)
    for old_key in _OLD_ENTITY_UNIQUE_IDS:
        for domain in ("number", "sensor", "switch", "select", "button", "text"):
            entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{old_key}")
            if entity_id is not None:
                registry.async_remove(entity_id)
                break

    # Existing installations may have stale categories from previous versions.
    # Keep the main dashboard short: target/mode/live values/status are primary;
    # tuning values are config; low-level PID output/cooling delta are diagnostic.
    for unique_key, category in _ENTITY_CATEGORY_BY_UNIQUE_KEY.items():
        domain = _ENTITY_DOMAIN_BY_UNIQUE_KEY[unique_key]
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{unique_key}")
        if entity_id is None:
            continue
        try:
            registry.async_update_entity(entity_id, entity_category=category)
        except TypeError:
            # Older HA versions may not support entity_category updates in migration.
            pass

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
