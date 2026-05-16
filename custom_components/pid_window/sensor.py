"""Sensors for PID Window Controller."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from . import RuntimeData


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    controller = runtime.controller
    sensors = [
        PidWindowSensor(controller, entry.entry_id, "current_temp", UnitOfTemperature.CELSIUS),
        PidWindowSensor(controller, entry.entry_id, "outdoor_temp", UnitOfTemperature.CELSIUS),
        PidWindowSensor(controller, entry.entry_id, "error", UnitOfTemperature.CELSIUS),
        PidWindowSensor(controller, entry.entry_id, "cover_position", "%"),
        PidWindowSensor(controller, entry.entry_id, "status", None, is_text=True),
        PidWindowSensor(controller, entry.entry_id, "cooling_delta", UnitOfTemperature.CELSIUS),
        PidWindowSensor(controller, entry.entry_id, "pid_output", "%"),
    ]
    async_add_entities(sensors)


class PidWindowSensor(SensorEntity):
    def __init__(self, controller, entry_id: str, key: str, unit: str | None, is_text: bool = False) -> None:
        self._controller = controller
        self._key = key
        self._is_text = is_text
        self._attr_has_entity_name = True
        self._attr_device_info = controller.device_info
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._remove_listener = controller.register_listener(self._handle_update)
        if key in {"cover_position", "pid_output"}:
            self._attr_suggested_display_precision = 0
        if key in {"cooling_delta", "pid_output"}:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key in {"current_temp", "outdoor_temp", "cooling_delta", "error"}:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "cover_position":
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:window-open"
        elif key == "status":
            self._attr_icon = "mdi:information-outline"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        if self._key == "cooling_delta":
            return self._controller.state.cooling_delta is not None
        if self._key == "error":
            return self._controller.state.error is not None
        return True

    @property
    def native_value(self):
        value = getattr(self._controller.state, self._key)
        if self._is_text:
            return value
        return None if value is None else round(float(value), 1)
