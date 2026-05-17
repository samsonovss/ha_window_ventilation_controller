"""Window Ventilation Controller integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, DEFAULT_KD, DEFAULT_KI, DEFAULT_KP
from .controller import PidWindowController

PLATFORMS = ["number", "sensor", "select", "switch"]


@dataclass
class RuntimeData:
    controller: PidWindowController


_AC_ENTITY_UNIQUE_IDS = ("ac_conflict_protection",)

_CO2_ENTITY_UNIQUE_IDS = (
    "co2_ventilation",
    "co2",
    "co2_status",
    "co2_position",
    "co2_threshold",
    "co2_hysteresis",
    "co2_ventilation_position",
    "co2_no_effect_timeout",
    "co2_minimum_drop",
    "co2_indoor_guard_margin",
    "co2_cold_outdoor_threshold",
    "co2_cold_max_position",
)


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
    "pid_profile": EntityCategory.CONFIG,
    "ac_conflict_protection": None,
    "co2_ventilation": None,
    "current_temp": None,
    "outdoor_temp": None,
    "co2": None,
    "co2_status": None,
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
    "co2_threshold": EntityCategory.CONFIG,
    "co2_hysteresis": EntityCategory.CONFIG,
    "co2_ventilation_position": EntityCategory.CONFIG,
    "co2_no_effect_timeout": EntityCategory.CONFIG,
    "co2_minimum_drop": EntityCategory.CONFIG,
    "co2_indoor_guard_margin": EntityCategory.CONFIG,
    "co2_cold_outdoor_threshold": EntityCategory.CONFIG,
    "co2_cold_max_position": EntityCategory.CONFIG,
    "cooling_delta": EntityCategory.DIAGNOSTIC,
    "pid_output": EntityCategory.DIAGNOSTIC,
    "co2_position": EntityCategory.DIAGNOSTIC,
    "window": None,
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
    "pid_profile": "select",
    "ac_conflict_protection": "switch",
    "co2_ventilation": "select",
    "status": "sensor",
    "co2_status": "sensor",
    "co2": "sensor",
    "cooling_delta": "sensor",
    "error": "sensor",
    "current_temp": "sensor",
    "outdoor_temp": "sensor",
    "cover_position": "sensor",
    "pid_output": "sensor",
    "co2_position": "sensor",
    "co2_threshold": "number",
    "co2_hysteresis": "number",
    "co2_ventilation_position": "number",
    "co2_no_effect_timeout": "number",
    "co2_minimum_drop": "number",
    "co2_indoor_guard_margin": "number",
    "co2_cold_outdoor_threshold": "number",
    "co2_cold_max_position": "number",
    "window": "cover",
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


def _remove_entities_by_unique_keys(registry: er.EntityRegistry, entry_id: str, unique_keys: tuple[str, ...]) -> None:
    for unique_key in unique_keys:
        domain = _ENTITY_DOMAIN_BY_UNIQUE_KEY.get(unique_key)
        if domain is None:
            continue
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry_id}_{unique_key}")
        if entity_id is not None:
            registry.async_remove(entity_id)


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
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=8)

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
    registry = er.async_get(hass)
    legacy_co2_switch = registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_co2_ventilation")
    if legacy_co2_switch is not None:
        registry.async_remove(legacy_co2_switch)
    if controller.ac_climate_entity is None:
        _remove_entities_by_unique_keys(registry, entry.entry_id, _AC_ENTITY_UNIQUE_IDS)
    if controller.co2_sensor is None:
        _remove_entities_by_unique_keys(registry, entry.entry_id, _CO2_ENTITY_UNIQUE_IDS)
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
