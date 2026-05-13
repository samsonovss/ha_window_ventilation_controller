"""Runtime controller for PID Window Controller."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_ADAPTIVE_OUTDOOR_FACTOR,
    CONF_ADAPTIVE_RATE_FACTOR,
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
    CONF_PROFILE_MODE,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_SUMMER_KD,
    CONF_SUMMER_KI,
    CONF_SUMMER_KP,
    CONF_UPDATE_INTERVAL,
    CONF_WINTER_KD,
    CONF_WINTER_KI,
    CONF_WINTER_KP,
    DEFAULT_KD,
    DEFAULT_ADAPTIVE_OUTDOOR_FACTOR,
    DEFAULT_ADAPTIVE_RATE_FACTOR,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_MAX_POSITION,
    DEFAULT_MIN_POSITION,
    DEFAULT_OUTDOOR_LOCK_THRESHOLD,
    DEFAULT_OUTDOOR_SUMMER_LIMIT,
    DEFAULT_PROFILE_MODE,
    DEFAULT_TARGET_TEMP,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_SUMMER_KD,
    DEFAULT_SUMMER_KI,
    DEFAULT_SUMMER_KP,
    DEFAULT_WINTER_KD,
    DEFAULT_WINTER_KI,
    DEFAULT_WINTER_KP,
    PROFILE_AUTO,
    PROFILE_SUMMER,
    PROFILE_WINTER,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ControllerState:
    current_temp: float | None = None
    outdoor_temp: float | None = None
    cover_position: float | None = None
    pid_output: float | None = None
    error: float | None = None
    temperature_trend: float | None = None
    active_profile: str = DEFAULT_PROFILE_MODE
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
        self.profile_mode = str(options.get(CONF_PROFILE_MODE, data.get(CONF_PROFILE_MODE, DEFAULT_PROFILE_MODE)))
        self.target_temp = float(options.get(CONF_TARGET_TEMP, data.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)))
        self.kp = float(options.get(CONF_KP, data.get(CONF_KP, DEFAULT_KP)))
        self.ki = float(options.get(CONF_KI, data.get(CONF_KI, DEFAULT_KI)))
        self.kd = float(options.get(CONF_KD, data.get(CONF_KD, DEFAULT_KD)))
        self.winter_kp = float(options.get(CONF_WINTER_KP, data.get(CONF_WINTER_KP, DEFAULT_WINTER_KP)))
        self.winter_ki = float(options.get(CONF_WINTER_KI, data.get(CONF_WINTER_KI, DEFAULT_WINTER_KI)))
        self.winter_kd = float(options.get(CONF_WINTER_KD, data.get(CONF_WINTER_KD, DEFAULT_WINTER_KD)))
        self.summer_kp = float(options.get(CONF_SUMMER_KP, data.get(CONF_SUMMER_KP, DEFAULT_SUMMER_KP)))
        self.summer_ki = float(options.get(CONF_SUMMER_KI, data.get(CONF_SUMMER_KI, DEFAULT_SUMMER_KI)))
        self.summer_kd = float(options.get(CONF_SUMMER_KD, data.get(CONF_SUMMER_KD, DEFAULT_SUMMER_KD)))
        self.adaptive_outdoor_factor = float(options.get(CONF_ADAPTIVE_OUTDOOR_FACTOR, data.get(CONF_ADAPTIVE_OUTDOOR_FACTOR, DEFAULT_ADAPTIVE_OUTDOOR_FACTOR)))
        self.adaptive_rate_factor = float(options.get(CONF_ADAPTIVE_RATE_FACTOR, data.get(CONF_ADAPTIVE_RATE_FACTOR, DEFAULT_ADAPTIVE_RATE_FACTOR)))
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
        self._last_temp: float | None = None
        self._last_position: float | None = None
        self._last_sent_position: float | None = None
        self._last_update_tick: float | None = None
        self._sample_count = 0
        self._autotune_active = False
        self._autotune_task = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("pid_window", self.entry.entry_id)},
            name=self.entry.data.get("name", "PID Window Controller"),
            manufacturer="OpenClaw",
            model="PID Window Controller",
        )

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

    def _profile_from_context(self, current_temp: float | None, outdoor_temp: float | None, temperature_trend: float | None) -> str:
        if self.profile_mode in {PROFILE_WINTER, PROFILE_SUMMER}:
            return self.profile_mode
        if outdoor_temp is None:
            if temperature_trend is not None:
                return PROFILE_SUMMER if temperature_trend > 0.2 else PROFILE_WINTER
            if current_temp is not None:
                return PROFILE_SUMMER if current_temp >= self.target_temp else PROFILE_WINTER
            return PROFILE_WINTER
        if outdoor_temp >= self.outdoor_lock_threshold:
            return PROFILE_SUMMER
        if outdoor_temp >= self.outdoor_summer_limit:
            return PROFILE_SUMMER
        return PROFILE_WINTER

    def _profile_gains(self, profile: str) -> tuple[float, float, float]:
        if profile == PROFILE_SUMMER:
            return self.summer_kp, self.summer_ki, self.summer_kd
        return self.winter_kp, self.winter_ki, self.winter_kd

    def _adaptive_multiplier(self, outdoor_temp: float | None, temperature_trend: float | None) -> float:
        multiplier = 1.0
        if outdoor_temp is not None:
            # If outside is hotter than target, back off opening; if colder, allow more opening.
            outdoor_delta = self.target_temp - outdoor_temp
            multiplier += self.adaptive_outdoor_factor * max(-1.0, min(1.0, outdoor_delta / 10.0))
        if temperature_trend is not None:
            # Positive trend = room warming up, open more. Negative trend = room cooling down, open less.
            multiplier += self.adaptive_rate_factor * max(-1.0, min(1.0, temperature_trend / 2.0))
        return max(0.4, min(1.6, multiplier))

    async def _async_tick(self, _event: Event | None) -> None:
        current_temp = self._read_float(self.temp_sensor)
        outdoor_temp = self._read_float(self.outdoor_sensor) if self.outdoor_sensor else None
        cover_position = self._cover_position()

        dt_hours = max(self.update_interval, 15) / 3600.0
        temperature_trend = None if self._last_temp is None or current_temp is None else (current_temp - self._last_temp) / dt_hours

        self.state.current_temp = current_temp
        self.state.outdoor_temp = outdoor_temp
        self.state.cover_position = cover_position
        self.state.temperature_trend = temperature_trend
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
        active_profile = self._profile_from_context(current_temp, outdoor_temp, temperature_trend)
        self.state.active_profile = active_profile

        # If the room is too cold, close the window fully.
        if error <= 0.0:
            self._integral = 0.0
            self._previous_error = error
            self._last_temp = current_temp
            target_position = float(self.min_position)
            self.state.pid_output = target_position
            self.state.status = "closing"
            await self._set_cover_position(target_position)
            self._notify()
            return

        self._integral += error * dt_hours
        self._integral = max(-20.0, min(20.0, self._integral))
        derivative = 0.0 if self._previous_error is None else (error - self._previous_error) / dt_hours

        kp, ki, kd = self._profile_gains(active_profile)
        output = kp * error + ki * self._integral + kd * derivative
        output *= self._adaptive_multiplier(outdoor_temp, temperature_trend)
        output = max(self.min_position, min(self.max_position, output))
        output = self._season_limit(outdoor_temp, output)
        output = max(self.min_position, min(self.max_position, output))

        self._previous_error = error
        self._last_temp = current_temp
        self._sample_count += 1
        self._last_update_tick = self.hass.loop.time()
        self._last_position = output
        self.state.pid_output = output
        self.state.status = "tuning" if self._autotune_active else f"controlling_{active_profile}"
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

    async def async_set_profile_mode(self, mode: str) -> None:
        self.profile_mode = mode
        self._async_save_option(CONF_PROFILE_MODE, mode)
        self._notify()
        await self._async_tick(None)

    async def async_set_gain(self, key: str, value: float) -> None:
        setattr(self, key, value)
        self._async_save_option(key, value)
        self._notify()
        await self._async_tick(None)

    async def async_autotune(self) -> None:
        if self._autotune_active:
            return
        self._autotune_task = self.hass.async_create_task(self._async_autotune_run())

    async def _async_autotune_run(self) -> None:
        current = self._read_float(self.temp_sensor)
        outdoor_temp = self._read_float(self.outdoor_sensor) if self.outdoor_sensor else None
        if current is None:
            self.state.status = "autotune_no_temperature"
            self._notify()
            return

        active_profile = self._profile_from_context(current, outdoor_temp, None if self._last_temp is None else current - self._last_temp)
        current_position = self._cover_position()
        if current_position is None:
            current_position = float(self.min_position)

        self._autotune_active = True
        self.state.autotune_running = True
        self.state.status = f"autotune_prepare_{active_profile}"
        self._notify()

        step = 12.0
        direction = 1.0 if current >= self.target_temp else -1.0
        test_position = max(self.min_position, min(self.max_position, current_position + step * direction))
        if abs(test_position - current_position) < 1.0:
            self.state.status = "autotune_no_room_for_step"
            self._autotune_active = False
            self.state.autotune_running = False
            self._notify()
            return

        start_temp = current
        await self._set_cover_position(test_position)
        self.state.status = f"autotune_sampling_{active_profile}"
        self._notify()

        sample_seconds = max(180, self.update_interval * 4)
        start_monotonic = self.hass.loop.time()
        samples: list[float] = []
        elapsed = 0.0
        while elapsed < sample_seconds:
            await asyncio.sleep(max(15, self.update_interval))
            now = self._read_float(self.temp_sensor)
            if now is not None:
                samples.append(now)
                self.state.current_temp = now
                self.state.status = f"autotune_sampling_{active_profile}_{len(samples)}"
                self._notify()
            elapsed = self.hass.loop.time() - start_monotonic

        end_temp = samples[-1] if samples else self._read_float(self.temp_sensor)
        if end_temp is None:
            end_temp = start_temp

        delta_pos = test_position - current_position
        delta_temp = end_temp - start_temp
        effect = abs(delta_temp) / max(abs(delta_pos), 1.0)
        intended = (current >= self.target_temp and delta_temp < 0) or (current < self.target_temp and delta_temp > 0)
        elapsed_hours = max((self.hass.loop.time() - start_monotonic) / 3600.0, 1 / 3600.0)

        if not intended or effect < 0.005:
            kp, ki, kd = (self.summer_kp, self.summer_ki, self.summer_kd) if active_profile == PROFILE_SUMMER else (self.winter_kp, self.winter_ki, self.winter_kd)
            self.state.status = f"autotune_noisy_{active_profile}"
        else:
            kp = max(4.0, min(40.0, 1.5 / max(effect, 0.01)))
            ki = max(0.03, min(0.8, kp / max(elapsed_hours * 12.0, 8.0)))
            kd = max(0.0, min(3.0, kp * min(elapsed_hours, 0.5) / 3.0))
            self.state.status = f"autotune_done_{active_profile}"

        if active_profile == PROFILE_SUMMER:
            self.summer_kp, self.summer_ki, self.summer_kd = kp, ki, kd
            self._async_save_option(CONF_SUMMER_KP, kp)
            self._async_save_option(CONF_SUMMER_KI, ki)
            self._async_save_option(CONF_SUMMER_KD, kd)
        else:
            self.winter_kp, self.winter_ki, self.winter_kd = kp, ki, kd
            self._async_save_option(CONF_WINTER_KP, kp)
            self._async_save_option(CONF_WINTER_KI, ki)
            self._async_save_option(CONF_WINTER_KD, kd)

        await self._set_cover_position(current_position)
        self._autotune_active = False
        self.state.autotune_running = False
        self.state.active_profile = active_profile
        self._notify()
        await self._async_tick(None)

    @property
    def available(self) -> bool:
        return self._enabled

    @property
    def sample_count(self) -> int:
        return self._sample_count
