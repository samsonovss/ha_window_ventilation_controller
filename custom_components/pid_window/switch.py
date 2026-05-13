"""Switches for PID Window Controller."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from . import RuntimeData


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PidWindowEnableSwitch(runtime.controller, entry.entry_id),
        PidWindowOutdoorLockSwitch(runtime.controller, entry.entry_id),
        PidWindowTempSensorGuardSwitch(runtime.controller, entry.entry_id),
    ])


class PidWindowEnableSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_name = "PID Window Enabled"
        self._attr_unique_id = f"{entry_id}_enabled"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._controller.state.enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._controller.async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._controller.async_set_enabled(False)


class PidWindowOutdoorLockSwitch(SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_name = "Outdoor lock enabled"
        self._attr_unique_id = f"{entry_id}_outdoor_lock_enabled"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._controller.enable_outdoor_lock

    async def async_turn_on(self, **kwargs) -> None:
        await self._controller.async_set_outdoor_lock_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._controller.async_set_outdoor_lock_enabled(False)


class PidWindowTempSensorGuardSwitch(SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_name = "Temp sensor guard"
        self._attr_unique_id = f"{entry_id}_temp_sensor_guard"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._controller.enable_temp_sensor_guard

    async def async_turn_on(self, **kwargs) -> None:
        await self._controller.async_set_temp_sensor_guard_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._controller.async_set_temp_sensor_guard_enabled(False)
