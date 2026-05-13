"""Config flow for PID Window Controller."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COVER_ENTITY,
    CONF_ENABLE_OUTDOOR_LOCK,
    CONF_MAX_POSITION,
    CONF_MIN_POSITION,
    CONF_OUTDOOR_LOCK_THRESHOLD,
    CONF_OUTDOOR_SENSOR,
    CONF_OUTDOOR_SUMMER_LIMIT,
    CONF_PROFILE_MODE,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_AUTOTUNE_SAMPLE_SECONDS,
    CONF_CALIBRATION_POINTS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MAX_POSITION,
    DEFAULT_MIN_POSITION,
    DEFAULT_NAME,
    DEFAULT_OUTDOOR_LOCK_THRESHOLD,
    DEFAULT_OUTDOOR_SUMMER_LIMIT,
    DEFAULT_PROFILE_MODE,
    DEFAULT_TARGET_TEMP,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_AUTOTUNE_SAMPLE_SECONDS,
    DEFAULT_CALIBRATION_POINTS,
    PROFILE_AUTO,
    PROFILE_SUMMER,
    PROFILE_WINTER,
    DOMAIN,
)


def _schema(data: dict | None = None) -> vol.Schema:
    data = data or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_TEMP_SENSOR, default=data.get(CONF_TEMP_SENSOR, "")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_COVER_ENTITY, default=data.get(CONF_COVER_ENTITY, "")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="cover")
            ),
            vol.Optional(CONF_OUTDOOR_SENSOR, default=data.get(CONF_OUTDOOR_SENSOR, "")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_TARGET_TEMP, default=data.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=16, max=30, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_PROFILE_MODE, default=data.get(CONF_PROFILE_MODE, DEFAULT_PROFILE_MODE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[PROFILE_AUTO, PROFILE_WINTER, PROFILE_SUMMER],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_AUTOTUNE_SAMPLE_SECONDS, default=data.get(CONF_AUTOTUNE_SAMPLE_SECONDS, DEFAULT_AUTOTUNE_SAMPLE_SECONDS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=60, max=900, step=30, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_CALIBRATION_POINTS, default=data.get(CONF_CALIBRATION_POINTS, DEFAULT_CALIBRATION_POINTS)): selector.TextSelector(
                selector.TextSelectorConfig(multiline=False)
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
