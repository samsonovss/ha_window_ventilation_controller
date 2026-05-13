"""PID Window Controller integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .controller import PidWindowController

PLATFORMS = ["switch", "number", "sensor", "button"]


@dataclass
class RuntimeData:
    controller: PidWindowController


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
