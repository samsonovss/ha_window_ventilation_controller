"""Numbers for Window Ventilation Controller."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_CO2_COLD_MAX_POSITION,
    CONF_CO2_COLD_OUTDOOR_THRESHOLD,
    CONF_CO2_HYSTERESIS,
    CONF_CO2_INDOOR_GUARD_MARGIN,
    CONF_CO2_MINIMUM_DROP,
    CONF_CO2_NO_EFFECT_TIMEOUT,
    CONF_CO2_THRESHOLD,
    CONF_CO2_VENTILATION_POSITION,
    DOMAIN,
)
from . import RuntimeData


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    controller = runtime.controller
    numbers = [
        PidWindowNumber(controller, entry.entry_id, "target_temp", 16.0, 30.0, 0.1, UnitOfTemperature.CELSIUS, category=None),
        PidWindowNumber(controller, entry.entry_id, "temp_deadband", 0.0, 2.0, 0.1, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "cooling_delta_threshold", 3.0, 20.0, 0.5, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "cooling_delta_hysteresis", 0.0, 5.0, 0.5, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "position_change_threshold", 0.0, 10.0, 0.5, "%"),
        PidWindowNumber(controller, entry.entry_id, "kp", 0.0, 50.0, 0.1, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "ki", 0.0, 7200.0, 30.0, "s"),
        PidWindowNumber(controller, entry.entry_id, "kd", 0.0, 1800.0, 30.0, "s"),
        PidWindowNumber(controller, entry.entry_id, "update_interval", 15.0, 600.0, 15.0, None),
    ]
    if controller.co2_sensor:
        numbers.extend([
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_THRESHOLD, 600.0, 2000.0, 50.0, "ppm"),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_HYSTERESIS, 0.0, 500.0, 50.0, "ppm"),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_VENTILATION_POSITION, 0.0, 100.0, 5.0, "%"),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_NO_EFFECT_TIMEOUT, 1.0, 60.0, 1.0, "min"),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_MINIMUM_DROP, 0.0, 300.0, 10.0, "ppm"),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_INDOOR_GUARD_MARGIN, 0.0, 2.0, 0.1, UnitOfTemperature.CELSIUS),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_COLD_OUTDOOR_THRESHOLD, -30.0, 30.0, 1.0, UnitOfTemperature.CELSIUS),
            PidWindowNumber(controller, entry.entry_id, CONF_CO2_COLD_MAX_POSITION, 0.0, 100.0, 5.0, "%"),
        ])
    async_add_entities(numbers)


class PidWindowNumber(NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str, key: str, min_value: float, max_value: float, step: float, unit: str | None, category=EntityCategory.CONFIG) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_category = category

    @property
    def native_value(self):
        return float(getattr(self._controller, self._key))

    async def async_set_native_value(self, value: float) -> None:
        if self._key == "target_temp":
            await self._controller.async_set_target_temp(float(value))
            return
        if self._key == "update_interval":
            await self._controller.async_set_update_interval(int(value))
            return
        if self._key == "cooling_delta_threshold":
            await self._controller.async_set_cooling_delta_threshold(float(value))
            return
        if self._key == "cooling_delta_hysteresis":
            await self._controller.async_set_cooling_delta_hysteresis(float(value))
            return
        if self._key == "temp_deadband":
            await self._controller.async_set_temp_deadband(float(value))
            return
        if self._key == "position_change_threshold":
            await self._controller.async_set_position_change_threshold(float(value))
            return
        if self._key.startswith("co2_"):
            await self._controller.async_set_co2_number(self._key, float(value))
            return

        await self._controller.async_set_gain(self._key, float(value))
