"""Config flow for PID Window Controller."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_COVER_ENTITY,
    CONF_ENABLE_OUTDOOR_LOCK,
    CONF_KD,
    CONF_KI,
    CONF_KP,
    CONF_MAX_POSITION,
    CONF_MIN_POSITION,
    CONF_OUTDOOR_LOCK_THRESHOLD,
    CONF_OUTDOOR_SENSOR,
    CONF_OUTDOOR_SUMMER_LIMIT,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_KD,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_MAX_POSITION,
    DEFAULT_MIN_POSITION,
    DEFAULT_NAME,
    DEFAULT_OUTDOOR_LOCK_THRESHOLD,
    DEFAULT_OUTDOOR_SUMMER_LIMIT,
    DEFAULT_TARGET_TEMP,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


def _schema(data: dict | None = None) -> vol.Schema:
    data = data or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): cv.string,
            vol.Required(CONF_TEMP_SENSOR, default=data.get(CONF_TEMP_SENSOR, "")): cv.string,
            vol.Required(CONF_COVER_ENTITY, default=data.get(CONF_COVER_ENTITY, "")): cv.string,
            vol.Optional(CONF_OUTDOOR_SENSOR, default=data.get(CONF_OUTDOOR_SENSOR, "")): cv.string,
            vol.Required(CONF_TARGET_TEMP, default=data.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=16, max=30, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_KP, default=data.get(CONF_KP, DEFAULT_KP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=50, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_KI, default=data.get(CONF_KI, DEFAULT_KI)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=5, step=0.01, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_KD, default=data.get(CONF_KD, DEFAULT_KD)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=10, step=0.01, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_UPDATE_INTERVAL, default=data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=15, max=600, step=15, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_MIN_POSITION, default=data.get(CONF_MIN_POSITION, DEFAULT_MIN_POSITION)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required(CONF_MAX_POSITION, default=data.get(CONF_MAX_POSITION, DEFAULT_MAX_POSITION)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER)
            ),
            vol.Required(CONF_ENABLE_OUTDOOR_LOCK, default=data.get(CONF_ENABLE_OUTDOOR_LOCK, False)): selector.BooleanSelector(),
            vol.Required(CONF_OUTDOOR_SUMMER_LIMIT, default=data.get(CONF_OUTDOOR_SUMMER_LIMIT, DEFAULT_OUTDOOR_SUMMER_LIMIT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-20, max=40, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_OUTDOOR_LOCK_THRESHOLD, default=data.get(CONF_OUTDOOR_LOCK_THRESHOLD, DEFAULT_OUTDOOR_LOCK_THRESHOLD)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-10, max=50, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
        }
    )


class PidWindowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PidWindowOptionsFlow(config_entry)


class PidWindowOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema({**self.config_entry.data, **self.config_entry.options}))
