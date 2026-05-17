"""Config flow for Window Ventilation Controller."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_AC_CLIMATE_ENTITY,
    CONF_CO2_SENSOR,
    CONF_COVER_ENTITY,
    CONF_OUTDOOR_SENSOR,
    CONF_TEMP_SENSOR,
    DEFAULT_NAME,
    DOMAIN,
)


def _normalize_options(data: dict) -> dict:
    normalized = dict(data)
    for key in (CONF_OUTDOOR_SENSOR, CONF_AC_CLIMATE_ENTITY, CONF_CO2_SENSOR):
        if not normalized.get(key):
            normalized.pop(key, None)
    return normalized


def _entity_options(hass: HomeAssistant, domain: str, current: str | None = None) -> list[dict[str, str]]:
    options = [{"value": "", "label": "-"}]
    entity_ids = sorted(hass.states.async_entity_ids(domain))
    if current and current not in entity_ids:
        entity_ids.insert(0, current)
    options.extend({"value": entity_id, "label": entity_id} for entity_id in entity_ids)
    return options


def _options_schema(hass: HomeAssistant, data: dict | None = None) -> dict:
    data = data or {}
    return {
        vol.Required(CONF_TEMP_SENSOR, default=data.get(CONF_TEMP_SENSOR, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_OUTDOOR_SENSOR, default=data.get(CONF_OUTDOOR_SENSOR, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_AC_CLIMATE_ENTITY, default=data.get(CONF_AC_CLIMATE_ENTITY, "")): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_entity_options(hass, "climate", data.get(CONF_AC_CLIMATE_ENTITY)),
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_CO2_SENSOR, default=data.get(CONF_CO2_SENSOR, "")): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_entity_options(hass, "sensor", data.get(CONF_CO2_SENSOR)),
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_COVER_ENTITY, default=data.get(CONF_COVER_ENTITY, "")): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="cover")
        ),
    }


def _schema(hass: HomeAssistant, data: dict | None = None) -> vol.Schema:
    return vol.Schema(_options_schema(hass, data))


def _config_options_schema(hass: HomeAssistant, data: dict | None = None) -> vol.Schema:
    return vol.Schema(_options_schema(hass, data))


class PidWindowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 8

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=DEFAULT_NAME, data=_normalize_options(user_input))
        return self.async_show_form(step_id="user", data_schema=_schema(self.hass), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PidWindowOptionsFlow()


class PidWindowOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=_normalize_options(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_config_options_schema(self.hass, {**self.config_entry.data, **self.config_entry.options}),
        )
