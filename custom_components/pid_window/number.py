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
        PidWindowNumber(controller, entry.entry_id, "target_temp", "Target temperature", 16.0, 30.0, 0.1, UnitOfTemperature.CELSIUS),
        PidWindowNumber(controller, entry.entry_id, "kp", "PID Kp", 0.0, 50.0, 0.1, None),
        PidWindowNumber(controller, entry.entry_id, "ki", "PID Ki", 0.0, 5.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "kd", "PID Kd", 0.0, 10.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "winter_kp", "Winter Kp", 0.0, 50.0, 0.1, None),
        PidWindowNumber(controller, entry.entry_id, "winter_ki", "Winter Ki", 0.0, 5.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "winter_kd", "Winter Kd", 0.0, 10.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "summer_kp", "Summer Kp", 0.0, 50.0, 0.1, None),
        PidWindowNumber(controller, entry.entry_id, "summer_ki", "Summer Ki", 0.0, 5.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "summer_kd", "Summer Kd", 0.0, 10.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "adaptive_outdoor_factor", "Adaptive outdoor factor", 0.0, 1.0, 0.01, None),
        PidWindowNumber(controller, entry.entry_id, "adaptive_rate_factor", "Adaptive rate factor", 0.0, 1.0, 0.01, None),
    ])


class PidWindowNumber(NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str, key: str, name: str, min_value: float, max_value: float, step: float, unit: str | None) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return float(getattr(self._controller, self._key))

    async def async_set_native_value(self, value: float) -> None:
        if self._key == "target_temp":
            await self._controller.async_set_target_temp(float(value))
            return

        await self._controller.async_set_gain(self._key, float(value))
