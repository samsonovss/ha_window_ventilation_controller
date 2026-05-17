"""Switches for Window Ventilation Controller."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback

from . import RuntimeData
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    controller = runtime.controller
    switches = []
    if controller.ac_climate_entity:
        switches.append(PidWindowSwitch(controller, entry.entry_id, "ac_conflict_protection"))
    async_add_entities(switches)


class PidWindowSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, controller, entry_id: str, key: str) -> None:
        self._controller = controller
        self._key = key
        self._attr_device_info = controller.device_info
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._remove_listener = controller.register_listener(self._handle_update)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._remove_listener)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return bool(getattr(self._controller, self._key))

    async def async_turn_on(self, **kwargs) -> None:
        await self._controller.async_set_ac_conflict_protection(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._controller.async_set_ac_conflict_protection(False)
