"""Config flow for PID Window Controller."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COOLING_DELTA_HYSTERESIS,
    CONF_COOLING_DELTA_THRESHOLD,
    CONF_COVER_ENTITY,
    CONF_MAX_POSITION,
    CONF_MIN_POSITION,
    CONF_OUTDOOR_SENSOR,
    CONF_POSITION_CHANGE_THRESHOLD,
    CONF_COOLING_MODE,
    CONF_KD,
    CONF_KI,
    CONF_KP,
    CONF_TARGET_TEMP,
    CONF_TEMP_DEADBAND,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MAX_POSITION,
    DEFAULT_MIN_POSITION,
    DEFAULT_NAME,
    DEFAULT_POSITION_CHANGE_THRESHOLD,
    DEFAULT_COOLING_MODE,
    DEFAULT_KD,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_TARGET_TEMP,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_COOLING_DELTA_HYSTERESIS,
    DEFAULT_COOLING_DELTA_THRESHOLD,
    DEFAULT_TEMP_DEADBAND,
    COOLING_MODE_AUTO,
    COOLING_MODE_DISABLED,
    COOLING_MODE_FORCE,
    DOMAIN,
)


def _cooling_mode_default(data: dict) -> str:
    mode = data.get(CONF_COOLING_MODE, data.get("profile_mode", DEFAULT_COOLING_MODE))
    if mode not in {COOLING_MODE_DISABLED, COOLING_MODE_FORCE, COOLING_MODE_AUTO}:
        return DEFAULT_COOLING_MODE
    return str(mode)


def _base_schema(data: dict | None = None) -> dict:
    data = data or {}
    return {
        vol.Required(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
    }


def _options_schema(data: dict | None = None) -> dict:
    data = data or {}
    return {
        vol.Required(CONF_TEMP_SENSOR, default=data.get(CONF_TEMP_SENSOR, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_COVER_ENTITY, default=data.get(CONF_COVER_ENTITY, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="cover")
        ),
        vol.Optional(CONF_OUTDOOR_SENSOR, default=data.get(CONF_OUTDOOR_SENSOR, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
    }


def _control_schema(data: dict | None = None) -> dict:
    data = data or {}
    return {
        vol.Required(CONF_TARGET_TEMP, default=data.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=16, max=30, step=0.1, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_KP, default=data.get(CONF_KP, data.get("winter_kp", DEFAULT_KP))): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=50, step=0.1, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_KI, default=data.get(CONF_KI, data.get("winter_ki", DEFAULT_KI))): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=7200, step=30, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_KD, default=data.get(CONF_KD, data.get("winter_kd", DEFAULT_KD))): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=1800, step=30, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_COOLING_MODE, default=_cooling_mode_default(data)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[COOLING_MODE_DISABLED, COOLING_MODE_FORCE, COOLING_MODE_AUTO],
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key=CONF_COOLING_MODE,
            )
        ),
        vol.Required(CONF_COOLING_DELTA_THRESHOLD, default=data.get(CONF_COOLING_DELTA_THRESHOLD, DEFAULT_COOLING_DELTA_THRESHOLD)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=3, max=20, step=0.5, mode=selector.NumberSelectorMode.SLIDER)
        ),
        vol.Required(CONF_COOLING_DELTA_HYSTERESIS, default=data.get(CONF_COOLING_DELTA_HYSTERESIS, DEFAULT_COOLING_DELTA_HYSTERESIS)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=5, step=0.5, mode=selector.NumberSelectorMode.SLIDER)
        ),
        vol.Required(CONF_TEMP_DEADBAND, default=data.get(CONF_TEMP_DEADBAND, DEFAULT_TEMP_DEADBAND)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=2, step=0.1, mode=selector.NumberSelectorMode.SLIDER)
        ),
        vol.Required(CONF_POSITION_CHANGE_THRESHOLD, default=data.get(CONF_POSITION_CHANGE_THRESHOLD, DEFAULT_POSITION_CHANGE_THRESHOLD)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=10, step=0.5, mode=selector.NumberSelectorMode.SLIDER)
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
    }


def _schema(data: dict | None = None) -> vol.Schema:
    return vol.Schema({**_base_schema(data), **_options_schema(data), **_control_schema(data)})


def _config_options_schema(data: dict | None = None) -> vol.Schema:
    return vol.Schema(_options_schema(data))


class PidWindowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 7

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PidWindowOptionsFlow()


class PidWindowOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_config_options_schema({**self.config_entry.data, **self.config_entry.options}),
        )
