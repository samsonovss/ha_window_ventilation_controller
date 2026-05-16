"""Runtime controller for PID Window Controller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AC_CLIMATE_ENTITY,
    CONF_AC_CONFLICT_PROTECTION,
    CONF_COOLING_DELTA_HYSTERESIS,
    CONF_COOLING_DELTA_THRESHOLD,
    CONF_COOLING_MODE,
    CONF_KD,
    CONF_KI,
    CONF_KP,
    CONF_PID_PROFILE,
    CONF_COVER_ENTITY,
    CONF_MAX_POSITION,
    CONF_MIN_POSITION,
    CONF_OUTDOOR_SENSOR,
    CONF_POSITION_CHANGE_THRESHOLD,
    CONF_TARGET_TEMP,
    CONF_TEMP_DEADBAND,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_COOLING_DELTA_HYSTERESIS,
    DEFAULT_COOLING_DELTA_THRESHOLD,
    DEFAULT_AC_CONFLICT_PROTECTION,
    DEFAULT_COOLING_MODE,
    DEFAULT_KD,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_PID_PROFILE,
    DEFAULT_MAX_POSITION,
    DEFAULT_MIN_POSITION,
    DEFAULT_POSITION_CHANGE_THRESHOLD,
    DEFAULT_TARGET_TEMP,
    DEFAULT_TEMP_DEADBAND,
    DEFAULT_UPDATE_INTERVAL,
    COOLING_MODE_AUTO,
    COOLING_MODE_DISABLED,
    COOLING_MODE_FORCE,
    PID_PROFILE_AGGRESSIVE,
    PID_PROFILE_MANUAL,
    PID_PROFILE_NORMAL,
    PID_PROFILE_PRESETS,
    PID_PROFILE_SOFT,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ControllerState:
    current_temp: float | None = None
    outdoor_temp: float | None = None
    cooling_delta: float | None = None
    cover_position: float | None = None
    pid_output: float | None = None
    error: float | None = None
    enabled: bool = True
    status: str = "idle"


class PidWindowController:
    """PID controller state and periodic update loop."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        data = entry.data
        options = entry.options

        self.temp_sensor = options.get(CONF_TEMP_SENSOR, data[CONF_TEMP_SENSOR])
        self.cover_entity = options.get(CONF_COVER_ENTITY, data[CONF_COVER_ENTITY])
        self.ac_climate_entity = options.get(CONF_AC_CLIMATE_ENTITY, data.get(CONF_AC_CLIMATE_ENTITY)) or None
        self.ac_conflict_protection = bool(
            options.get(
                CONF_AC_CONFLICT_PROTECTION,
                data.get(CONF_AC_CONFLICT_PROTECTION, DEFAULT_AC_CONFLICT_PROTECTION),
            )
        )
        self.outdoor_sensor = options.get(CONF_OUTDOOR_SENSOR, data.get(CONF_OUTDOOR_SENSOR)) or None
        self.cooling_mode = str(
            options.get(
                CONF_COOLING_MODE,
                data.get(CONF_COOLING_MODE, options.get("profile_mode", data.get("profile_mode", DEFAULT_COOLING_MODE))),
            )
        )
        if self.cooling_mode not in {COOLING_MODE_DISABLED, COOLING_MODE_FORCE, COOLING_MODE_AUTO}:
            self.cooling_mode = DEFAULT_COOLING_MODE
        # Backward compatibility for code/status that still talks about profiles.
        self.profile_mode = self.cooling_mode
        self.target_temp = float(options.get(CONF_TARGET_TEMP, data.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP)))
        self.kp = float(options.get(CONF_KP, data.get(CONF_KP, data.get("winter_kp", DEFAULT_KP))))
        self.ki = float(options.get(CONF_KI, data.get(CONF_KI, data.get("winter_ki", DEFAULT_KI))))
        self.kd = float(options.get(CONF_KD, data.get(CONF_KD, data.get("winter_kd", DEFAULT_KD))))
        self.update_interval = int(options.get(CONF_UPDATE_INTERVAL, data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)))
        self.min_position = int(options.get(CONF_MIN_POSITION, data.get(CONF_MIN_POSITION, DEFAULT_MIN_POSITION)))
        self.max_position = int(options.get(CONF_MAX_POSITION, data.get(CONF_MAX_POSITION, DEFAULT_MAX_POSITION)))
        self.temp_deadband = float(options.get(CONF_TEMP_DEADBAND, data.get(CONF_TEMP_DEADBAND, DEFAULT_TEMP_DEADBAND)))
        self.position_change_threshold = float(options.get(CONF_POSITION_CHANGE_THRESHOLD, data.get(CONF_POSITION_CHANGE_THRESHOLD, DEFAULT_POSITION_CHANGE_THRESHOLD)))
        self.cooling_delta_threshold = float(options.get(CONF_COOLING_DELTA_THRESHOLD, data.get(CONF_COOLING_DELTA_THRESHOLD, DEFAULT_COOLING_DELTA_THRESHOLD)))
        self.cooling_delta_hysteresis = float(options.get(CONF_COOLING_DELTA_HYSTERESIS, data.get(CONF_COOLING_DELTA_HYSTERESIS, DEFAULT_COOLING_DELTA_HYSTERESIS)))
        configured_pid_profile = options.get(CONF_PID_PROFILE, data.get(CONF_PID_PROFILE))
        if configured_pid_profile is None:
            self.pid_profile = self._matching_pid_profile()
        else:
            self.pid_profile = str(configured_pid_profile)
            if self.pid_profile not in {PID_PROFILE_MANUAL, PID_PROFILE_SOFT, PID_PROFILE_NORMAL, PID_PROFILE_AGGRESSIVE}:
                self.pid_profile = PID_PROFILE_MANUAL

        self.state = ControllerState()
        self._listeners: list[Callable[[], None]] = []
        self._unsub_interval = None
        self._unsub_ac_listener = None
        self._enabled = True
        self._integral = 0.0
        self._previous_error: float | None = None
        self._last_temp: float | None = None
        self._last_position: float | None = None
        self._last_sent_position: float | None = None
        self._last_update_tick: float | None = None
        self._sample_count = 0
        self._cooling_pid_allowed = False
        self._last_power = 0.0

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
        if self.ac_climate_entity:
            self._unsub_ac_listener = self.hass.bus.async_listen("state_changed", self._async_ac_state_changed)
        await self._async_tick(None)

    def _async_ac_state_changed(self, event: Event) -> None:
        if event.data.get("entity_id") != self.ac_climate_entity:
            return
        self.hass.async_create_task(self._async_tick(None))

    def _async_save_option(self, key: str, value: Any) -> None:
        options = {**self.entry.options, key: value}
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    def _async_save_options(self, values: dict[str, Any]) -> None:
        options = {**self.entry.options, **values}
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    def _matching_pid_profile(self) -> str:
        current = {
            CONF_KP: self.kp,
            CONF_KI: self.ki,
            CONF_KD: self.kd,
            CONF_POSITION_CHANGE_THRESHOLD: self.position_change_threshold,
        }
        for profile, preset in PID_PROFILE_PRESETS.items():
            if all(abs(float(current[key]) - float(preset[key])) < 0.0001 for key in current):
                return profile
        return PID_PROFILE_MANUAL

    async def async_stop(self) -> None:
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None
        if self._unsub_ac_listener:
            self._unsub_ac_listener()
            self._unsub_ac_listener = None

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

    def _cover_available(self) -> bool:
        state = self.hass.states.get(self.cover_entity)
        return state is not None and state.state not in {STATE_UNKNOWN, STATE_UNAVAILABLE, "none"}

    def _cover_position(self) -> float | None:
        state = self.hass.states.get(self.cover_entity)
        if state is None or state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, "none"}:
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

    def _ac_is_active(self) -> bool:
        if not self.ac_climate_entity or not self.ac_conflict_protection:
            return False
        state = self.hass.states.get(self.ac_climate_entity)
        if state is None or state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, "none"}:
            return False
        return state.state in {"cool", "dry", "heat_cool"}

    def _set_enabled_runtime(self, enabled: bool) -> None:
        self._enabled = enabled
        self.state.enabled = enabled
        self.state.status = "disabled" if not enabled else self.state.status
        self._notify()

    def _pid_gains(self) -> tuple[float, float, float]:
        return self.kp, self.ki, self.kd

    async def _async_tick(self, _event: Event | None) -> None:
        try:
            await self._async_tick_impl(_event)
        except Exception:  # noqa: BLE001 - keep the controller status safe for unexpected runtime errors.
            _LOGGER.exception("Unexpected PID window controller update error")
            self.state.status = "error"
            self._notify()

    async def _async_tick_impl(self, _event: Event | None) -> None:
        current_temp = self._read_float(self.temp_sensor)
        outdoor_temp = self._read_float(self.outdoor_sensor) if self.outdoor_sensor else None
        cooling_delta = None if current_temp is None or outdoor_temp is None else current_temp - outdoor_temp
        cover_available = self._cover_available()
        cover_position = self._cover_position() if cover_available else None

        self.state.current_temp = current_temp
        self.state.outdoor_temp = outdoor_temp
        self.state.cooling_delta = cooling_delta
        self.state.error = None if current_temp is None else current_temp - self.target_temp
        self.state.cover_position = cover_position
        self.state.enabled = self._enabled

        if current_temp is None:
            self.state.status = "temp_sensor_unavailable"
            self.state.pid_output = float(self.min_position)
            if cover_available:
                await self._set_cover_position(float(self.min_position))
            self._notify()
            return

        if not cover_available:
            self.state.status = "cover_unavailable"
            self._notify()
            return

        if self._ac_is_active():
            self._integral = 0.0
            self._previous_error = None
            self._last_temp = current_temp
            self._last_update_tick = None
            self.state.pid_output = float(self.min_position)
            self.state.status = "ac_active_window_closed"
            await self._set_cover_position(float(self.min_position), force=True)
            self._notify()
            return

        error = self.state.error
        if not self._enabled or self.cooling_mode == COOLING_MODE_DISABLED:
            self._integral = 0.0
            self._previous_error = None
            self._last_temp = current_temp
            self.state.pid_output = float(self.min_position)
            self.state.status = "disabled"
            await self._set_cover_position(float(self.min_position), force=True)
            self._notify()
            return

        if self.cooling_mode == COOLING_MODE_AUTO:
            if cooling_delta is None:
                self._cooling_pid_allowed = False
                self._integral = 0.0
                self._previous_error = None
                self._last_temp = current_temp
                self.state.pid_output = float(self.min_position)
                self.state.status = "outdoor_sensor_unavailable"
                await self._set_cover_position(float(self.min_position))
                self._notify()
                return

            if cooling_delta >= self.cooling_delta_threshold:
                self._cooling_pid_allowed = True
            elif cooling_delta <= self.cooling_delta_threshold - self.cooling_delta_hysteresis:
                self._cooling_pid_allowed = False

            if not self._cooling_pid_allowed:
                self._integral = 0.0
                self._previous_error = None
                self._last_temp = current_temp
                self.state.pid_output = float(self.min_position)
                self.state.status = "auto_blocked_by_delta"
                await self._set_cover_position(float(self.min_position))
                self._notify()
                return

        # If the room is at/below target, close the window fully.
        if current_temp <= self.target_temp:
            self._integral = 0.0
            self._previous_error = error
            self._last_temp = current_temp
            target_position = float(self.min_position)
            self.state.pid_output = target_position
            self.state.status = "idle"
            await self._set_cover_position(target_position)
            self._notify()
            return

        if self.temp_deadband > 0 and current_temp < self.target_temp + self.temp_deadband:
            self._previous_error = error
            self._last_temp = current_temp
            self.state.status = "deadband"
            self._notify()
            return

        now = self.hass.loop.time()
        delta_seconds = max(self.update_interval, 1)
        if self._last_update_tick is not None:
            delta_seconds = max(0.0, now - self._last_update_tick)

        prop_band, integral_time, derivative_time = self._pid_gains()
        range_width = max(1.0, float(self.max_position - self.min_position))
        integral_locked = False

        if prop_band <= 0:
            if error > 0:
                power = 1.0
            elif error < 0:
                power = 0.0
            else:
                power = self._last_power
        else:
            derivative = 0.0

            if self._previous_error is None or self._last_update_tick is None:
                # Same idea as node-red-contrib-pid integral_default=0.5: at setpoint, output starts at 50%.
                self._integral = 0.0
            elif delta_seconds <= 0 or delta_seconds > max(self.update_interval * 4, self.update_interval + 60):
                derivative = 0.0
                integral_locked = True
            else:
                derivative = derivative_time * (error - self._previous_error) / delta_seconds
                half_band = prop_band / 2.0
                if abs(error + self._integral) < half_band:
                    if integral_time <= 0:
                        self._integral = (1.0 if error > 0 else -1.0 if error < 0 else 0.0) * half_band
                    else:
                        self._integral += error * delta_seconds / integral_time
                else:
                    integral_locked = True

                self._integral = max(-half_band, min(half_band, self._integral))

            # Cooling form of node-red-contrib-pid: Node-RED heating output is inverted for cooling.
            # power is 0..1, then mapped to min/max cover position.
            power = 0.5 + ((error + self._integral + derivative) / prop_band)

        power = max(0.0, min(1.0, power))
        output = self.min_position + power * range_width
        output = max(self.min_position, min(self.max_position, output))

        self._previous_error = error
        self._last_temp = current_temp
        self._sample_count += 1
        self._last_update_tick = now
        self._last_power = power
        self._last_position = output
        self.state.pid_output = output
        self.state.status = "integral_locked" if integral_locked else "cooling"
        await self._set_cover_position(output)
        self._notify()

    async def _set_cover_position(self, position: float, *, force: bool = False) -> None:
        if position < self.min_position:
            position = float(self.min_position)
        if position > self.max_position:
            position = float(self.max_position)

        if (
            not force
            and self._last_sent_position is not None
            and abs(self._last_sent_position - position) < self.position_change_threshold
        ):
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
        self.state.cover_position = position
        self._notify()

    async def async_set_cover_position(self, position: float) -> None:
        await self._set_cover_position(position, force=True)

    async def async_set_target_temp(self, target_temp: float) -> None:
        self.target_temp = target_temp
        self._async_save_option(CONF_TARGET_TEMP, target_temp)
        self._notify()
        await self._async_tick(None)

    async def async_set_cooling_mode(self, mode: str) -> None:
        if mode not in {COOLING_MODE_DISABLED, COOLING_MODE_FORCE, COOLING_MODE_AUTO}:
            mode = DEFAULT_COOLING_MODE
        self.cooling_mode = mode
        self.profile_mode = mode
        self._async_save_option(CONF_COOLING_MODE, mode)
        self._notify()
        await self._async_tick(None)

    async def async_set_ac_conflict_protection(self, enabled: bool) -> None:
        self.ac_conflict_protection = bool(enabled)
        self._async_save_option(CONF_AC_CONFLICT_PROTECTION, self.ac_conflict_protection)
        self._notify()
        await self._async_tick(None)

    async def async_set_profile_mode(self, mode: str) -> None:
        await self.async_set_cooling_mode(mode)

    async def async_set_pid_profile(self, profile: str) -> None:
        if profile == PID_PROFILE_MANUAL:
            self.pid_profile = PID_PROFILE_MANUAL
            self._async_save_option(CONF_PID_PROFILE, PID_PROFILE_MANUAL)
            self._notify()
            return
        if profile not in PID_PROFILE_PRESETS:
            profile = DEFAULT_PID_PROFILE

        preset = PID_PROFILE_PRESETS[profile]
        self.kp = float(preset[CONF_KP])
        self.ki = float(preset[CONF_KI])
        self.kd = float(preset[CONF_KD])
        self.position_change_threshold = float(preset[CONF_POSITION_CHANGE_THRESHOLD])
        self.pid_profile = profile
        self._async_save_options({**preset, CONF_PID_PROFILE: profile})
        self._notify()
        await self._async_tick(None)

    async def async_set_gain(self, key: str, value: float) -> None:
        setattr(self, key, value)
        self.pid_profile = PID_PROFILE_MANUAL
        self._async_save_options({key: value, CONF_PID_PROFILE: PID_PROFILE_MANUAL})
        self._notify()
        await self._async_tick(None)

    async def async_set_update_interval(self, value: int) -> None:
        self.update_interval = int(value)
        self._async_save_option(CONF_UPDATE_INTERVAL, self.update_interval)
        await self.async_stop()
        await self.async_start()

    async def async_set_cooling_delta_threshold(self, value: float) -> None:
        self.cooling_delta_threshold = float(value)
        self._async_save_option(CONF_COOLING_DELTA_THRESHOLD, self.cooling_delta_threshold)
        self._notify()
        await self._async_tick(None)

    async def async_set_cooling_delta_hysteresis(self, value: float) -> None:
        self.cooling_delta_hysteresis = float(value)
        self._async_save_option(CONF_COOLING_DELTA_HYSTERESIS, self.cooling_delta_hysteresis)
        self._notify()
        await self._async_tick(None)

    async def async_set_temp_deadband(self, value: float) -> None:
        self.temp_deadband = float(value)
        self._async_save_option(CONF_TEMP_DEADBAND, self.temp_deadband)
        self._notify()
        await self._async_tick(None)

    async def async_set_position_change_threshold(self, value: float) -> None:
        self.position_change_threshold = float(value)
        self.pid_profile = PID_PROFILE_MANUAL
        self._async_save_options(
            {
                CONF_POSITION_CHANGE_THRESHOLD: self.position_change_threshold,
                CONF_PID_PROFILE: PID_PROFILE_MANUAL,
            }
        )
        self._notify()
        await self._async_tick(None)

    @property
    def available(self) -> bool:
        return self._enabled

    @property
    def sample_count(self) -> int:
        return self._sample_count
