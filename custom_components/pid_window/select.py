"""Selects for Window Ventilation Controller."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from .const import (
    COOLING_MODE_AUTO,
    COOLING_MODE_DISABLED,
    COOLING_MODE_FORCE,
    DOMAIN,
    PID_PROFILE_AGGRESSIVE,
    PID_PROFILE_MANUAL,
    PID_PROFILE_NORMAL,
    PID_PROFILE_SOFT,
)
from . import RuntimeData


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    selects = [
        PidWindowCoolingModeSelect(runtime.controller, entry.entry_id),
        PidWindowProfileSelect(runtime.controller, entry.entry_id),
    ]
    if runtime.controller.co2_sensor:
        selects.append(PidWindowCo2VentilationSelect(runtime.controller, entry.entry_id))
    async_add_entities(selects)


class PidWindowCoolingModeSelect(SelectEntity):
    _attr_options = [COOLING_MODE_DISABLED, COOLING_MODE_FORCE, COOLING_MODE_AUTO]
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_translation_key = "cooling_mode"
        self._attr_unique_id = f"{entry_id}_cooling_mode"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        return self._controller.cooling_mode

    async def async_select_option(self, option: str) -> None:
        await self._controller.async_set_cooling_mode(option)


class PidWindowProfileSelect(SelectEntity):
    _attr_options = [PID_PROFILE_SOFT, PID_PROFILE_NORMAL, PID_PROFILE_AGGRESSIVE, PID_PROFILE_MANUAL]
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_translation_key = "pid_profile"
        self._attr_unique_id = f"{entry_id}_pid_profile"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        return self._controller.pid_profile

    async def async_select_option(self, option: str) -> None:
        await self._controller.async_set_pid_profile(option)


class PidWindowCo2VentilationSelect(SelectEntity):
    _attr_options = [COOLING_MODE_DISABLED, COOLING_MODE_AUTO]
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str) -> None:
        self._controller = controller
        self._attr_device_info = controller.device_info
        self._attr_translation_key = "co2_ventilation"
        self._attr_unique_id = f"{entry_id}_co2_ventilation"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        return COOLING_MODE_AUTO if self._controller.co2_ventilation else COOLING_MODE_DISABLED

    async def async_select_option(self, option: str) -> None:
        await self._controller.async_set_co2_ventilation(option == COOLING_MODE_AUTO)
