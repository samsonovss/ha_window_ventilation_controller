"""Numbers for PID Window Controller."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from . import RuntimeData


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    controller = runtime.controller
    async_add_entities([
        PidWindowNumber(controller, entry.entry_id, "target_temp", "Target temperature", 16.0, 30.0, 0.1, UnitOfTemperature.CELSIUS, category=None),
        PidWindowNumber(controller, entry.entry_id, "temp_deadband", "Temperature deadband", 0.0, 2.0, 0.1, UnitOfTemperature.CELSIUS, category=None),
        PidWindowNumber(controller, entry.entry_id, "cooling_delta_threshold", "Cooling delta threshold", 3.0, 20.0, 0.5, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "cooling_delta_hysteresis", "Cooling delta hysteresis", 0.0, 5.0, 0.5, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "position_change_threshold", "Position change threshold", 0.0, 10.0, 0.5, "%"),
        PidWindowNumber(controller, entry.entry_id, "kp", "PID Kp", 0.0, 50.0, 0.1, None),
        PidWindowNumber(controller, entry.entry_id, "ki", "PID Ki", 0.0, 5.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "kd", "PID Kd", 0.0, 10.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "update_interval", "Update interval", 15.0, 600.0, 15.0, None),
    ])


class PidWindowNumber(NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str, key: str, name: str, min_value: float, max_value: float, step: float, unit: str | None, category=EntityCategory.CONFIG) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._key = key
        self._attr_name = name
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

        await self._controller.async_set_gain(self._key, float(value))
