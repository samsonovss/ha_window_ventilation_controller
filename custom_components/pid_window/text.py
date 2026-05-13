"""Text entities for PID Window Controller."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory

from . import RuntimeData
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PidWindowCalibrationText(runtime.controller, entry.entry_id)])


class PidWindowCalibrationText(TextEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = "text"
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_name = "Calibration points"
        self._attr_unique_id = f"{entry_id}_calibration_points"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @property
    def native_value(self) -> str:
        return self._controller.calibration_points_raw or ""

    @property
    def pattern(self) -> str | None:
        return None

    async def async_set_value(self, value: str) -> None:
        await self._controller.async_set_calibration_points(value)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
