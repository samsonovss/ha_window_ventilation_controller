"""Runtime controller for PID Window Controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

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
    DEFAULT_OUTDOOR_LOCK_THRESHOLD,
    DEFAULT_OUTDOOR_SUMMER_LIMIT,
    DEFAULT_TARGET_TEMP,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ControllerState:
    current_temp: float | None = None
    outdoor_temp: float | None = None
    cover_position: float | None = None
    pid_output: float | None = None
    error: float | None = None
    enabled: bool = True
    autotune_running: bool = False
    status: str = "idle"


class PidWindowController:
    """PID controller state and periodic update loop."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        data = entry.data
        options = entry.options

        self.temp_sensor = data[CONF_TEMP_SENSOR]
        self.cover_entity = data[CONF_COVER_ENTITY]
        self.outdoor_sensor = data.get(CONF_OUTDOOR_SENSOR) or options.get(CONF_OUTDOOR_SENSOR)
        self.target_temp = float(options.get(CONF_TARGET_TEMP, data.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)))
        self.kp = float(options.get(CONF_KP, data.get(CONF_KP, DEFAULT_KP)))
        self.ki = float(options.get(CONF_KI, data.get(CONF_KI, DEFAULT_KI)))
        self.kd = float(options.get(CONF_KD, data.get(CONF_KD, DEFAULT_KD)))
        self.update_interval = int(options.get(CONF_UPDATE_INTERVAL, data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)))
        self.min_position = int(options.get(CONF_MIN_POSITION, data.get(CONF_MIN_POSITION, DEFAULT_MIN_POSITION)))
        self.max_position = int(options.get(CONF_MAX_POSITION, data.get(CONF_MAX_POSITION, DEFAULT_MAX_POSITION)))
        self.enable_outdoor_lock = bool(options.get(CONF_ENABLE_OUTDOOR_LOCK, data.get(CONF_ENABLE_OUTDOOR_LOCK, False)))
        self.outdoor_summer_limit = float(options.get(CONF_OUTDOOR_SUMMER_LIMIT, data.get(CONF_OUTDOOR_SUMMER_LIMIT, DEFAULT_OUTDOOR_SUMMER_LIMIT)))
        self.outdoor_lock_threshold = float(options.get(CONF_OUTDOOR_LOCK_THRESHOLD, data.get(CONF_OUTDOOR_LOCK_THRESHOLD, DEFAULT_OUTDOOR_LOCK_THRESHOLD)))

        self.state = ControllerState()
        self._listeners: list[Callable[[], None]] = []
        self._unsub_interval = None
        self._enabled = True
        self._integral = 0.0
        self._previous_error: float | None = None
        self._last_position: float | None = None
        self._last_sent_position: float | None = None
        self._last_update_tick: float | None = None
        self._sample_count = 0
        self._autotune_active = False

    async def async_start(self) -> None:
        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._async_tick,
            timedelta(seconds=max(15, self.update_interval)),
        )
        await self._async_tick(None)

    def _async_save_option(self, key: str, value: Any) -> None:
        options = {**self.entry.options, key: value}
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def async_stop(self) -> None:
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None

    def register_listener(self, callback_fn: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(callback_fn)

        def remove() -> None:
            if callback_fn in self._listeners:
                self._listeners.remove(callback_fn)

        return remove

    def _notify(self) -> None:
        for callback_fn in list(self._listeners):
            callback_fn()

    def _read_float(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, "none"}:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _cover_position(self) -> float | None:
        state = self.hass.states.get(self.cover_entity)
        if state is None:
            return None
        attr = state.attributes.get("current_position")
        if attr is not None:
            try:
                return float(attr)
            except (TypeError, ValueError):
                pass
        if state.state == "open":
            return float(self.max_position)
        if state.state == "closed":
            return float(self.min_position)
        return None

    def _season_limit(self, outdoor_temp: float | None, desired: float) -> float:
        if outdoor_temp is None or not self.enable_outdoor_lock:
            return desired
        if outdoor_temp >= self.outdoor_lock_threshold:
            return float(self.min_position)
        if outdoor_temp >= self.outdoor_summer_limit:
            return min(desired, 30.0)
        return desired

    async def _async_tick(self, _event: Event | None) -> None:
        current_temp = self._read_float(self.temp_sensor)
        outdoor_temp = self._read_float(self.outdoor_sensor) if self.outdoor_sensor else None
        cover_position = self._cover_position()

        self.state.current_temp = current_temp
        self.state.outdoor_temp = outdoor_temp
        self.state.cover_position = cover_position
        self.state.enabled = self._enabled
        self.state.autotune_running = self._autotune_active

        if current_temp is None:
            self.state.status = "waiting_for_temperature"
            self._notify()
            return

        if not self._enabled:
            self.state.status = "disabled"
            self._notify()
            return

        error = current_temp - self.target_temp
        self.state.error = error

        # If the room is too cold, close the window fully.
        if error <= 0.0:
            self._integral = 0.0
            self._previous_error = error
            target_position = float(self.min_position)
            self.state.pid_output = target_position
            self.state.status = "closing"
            await self._set_cover_position(target_position)
            self._notify()
            return

        dt_hours = max(self.update_interval, 15) / 3600.0
        self._integral += error * dt_hours
        self._integral = max(-20.0, min(20.0, self._integral))
        derivative = 0.0 if self._previous_error is None else (error - self._previous_error) / dt_hours

        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        output = max(self.min_position, min(self.max_position, output))
        output = self._season_limit(outdoor_temp, output)
        output = max(self.min_position, min(self.max_position, output))

        self._previous_error = error
        self._sample_count += 1
        self._last_update_tick = self.hass.loop.time()
        self._last_position = output
        self.state.pid_output = output
        self.state.status = "tuning" if self._autotune_active else "controlling"
        await self._set_cover_position(output)
        self._notify()

    async def _set_cover_position(self, position: float) -> None:
        if position < self.min_position:
            position = float(self.min_position)
        if position > self.max_position:
            position = float(self.max_position)

        if self._last_sent_position is not None and abs(self._last_sent_position - position) < 1.0:
            return

        await self.hass.services.async_call(
            "cover",
            "set_cover_position",
            {
                "entity_id": self.cover_entity,
                "position": round(position),
            },
            blocking=False,
        )
        self._last_sent_position = position

    async def async_set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._async_save_option("enabled", enabled)
        self.state.enabled = enabled
        self.state.status = "disabled" if not enabled else self.state.status
        self._notify()
        if enabled:
            await self._async_tick(None)

    async def async_set_target_temp(self, target_temp: float) -> None:
        self.target_temp = target_temp
        self._async_save_option(CONF_TARGET_TEMP, target_temp)
        self._notify()
        await self._async_tick(None)

    async def async_set_gain(self, key: str, value: float) -> None:
        setattr(self, key, value)
        self._async_save_option(key, value)
        self._notify()
        await self._async_tick(None)

    async def async_autotune(self) -> None:
        current = self._read_float(self.temp_sensor)
        if current is None:
            raise ValueError("Current temperature is unavailable")
        self._autotune_active = True
        self.state.autotune_running = True
        self.state.status = "autotune_started"
        self._notify()
        # Conservative heuristic, safe for a window actuator.
        deviation = abs(current - self.target_temp)
        if deviation < 0.5:
            self.kp, self.ki, self.kd = DEFAULT_KP, DEFAULT_KI, DEFAULT_KD
        else:
            self.kp = max(4.0, min(25.0, 18.0 / deviation))
            self.ki = max(0.05, min(0.6, self.kp / 90.0))
            self.kd = max(0.0, min(2.0, self.kp / 12.0))
        self._async_save_option(CONF_KP, self.kp)
        self._async_save_option(CONF_KI, self.ki)
        self._async_save_option(CONF_KD, self.kd)
        self.state.status = "autotune_finished"
        self._autotune_active = False
        self.state.autotune_running = False
        self._notify()
        await self._async_tick(None)

    @property
    def available(self) -> bool:
        return self._enabled

    @property
    def sample_count(self) -> int:
        return self._sample_count
