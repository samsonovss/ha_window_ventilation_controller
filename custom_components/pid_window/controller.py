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
    CONF_AUTOTUNE_SAMPLE_SECONDS,
    CONF_AUTOTUNE_STEP,
    CONF_CALIBRATION_POINTS,
    CONF_COOLING_DELTA_HYSTERESIS,
    CONF_COOLING_DELTA_THRESHOLD,
    CONF_COOLING_MODE,
    CONF_KD,
    CONF_KI,
    CONF_KP,
    CONF_COVER_ENTITY,
    CONF_ENABLE_TEMP_DEADBAND,
    CONF_MAX_POSITION,
    CONF_MIN_POSITION,
    CONF_OUTDOOR_SENSOR,
    CONF_POSITION_CHANGE_THRESHOLD,
    CONF_TARGET_TEMP,
    CONF_TEMP_DEADBAND,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ADAPTIVE_OUTDOOR_FACTOR,
    DEFAULT_ADAPTIVE_RATE_FACTOR,
    DEFAULT_AUTOTUNE_SAMPLE_SECONDS,
    DEFAULT_CALIBRATION_POINTS,
    DEFAULT_COOLING_DELTA_HYSTERESIS,
    DEFAULT_COOLING_DELTA_THRESHOLD,
    DEFAULT_COOLING_MODE,
    DEFAULT_KD,
    DEFAULT_KI,
    DEFAULT_KP,
    DEFAULT_ENABLE_TEMP_DEADBAND,
    DEFAULT_MAX_POSITION,
    DEFAULT_MIN_POSITION,
    DEFAULT_POSITION_CHANGE_THRESHOLD,
    DEFAULT_TARGET_TEMP,
    DEFAULT_TEMP_DEADBAND,
    DEFAULT_UPDATE_INTERVAL,
    COOLING_MODE_AUTO,
    COOLING_MODE_DISABLED,
    COOLING_MODE_FORCE,
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
    temperature_trend: float | None = None
    last_autotune_result: str | None = None
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
        self.adaptive_outdoor_factor = float(options.get(CONF_ADAPTIVE_OUTDOOR_FACTOR, data.get(CONF_ADAPTIVE_OUTDOOR_FACTOR, DEFAULT_ADAPTIVE_OUTDOOR_FACTOR)))
        self.adaptive_rate_factor = float(options.get(CONF_ADAPTIVE_RATE_FACTOR, data.get(CONF_ADAPTIVE_RATE_FACTOR, DEFAULT_ADAPTIVE_RATE_FACTOR)))
        self.autotune_sample_seconds = int(options.get(CONF_AUTOTUNE_SAMPLE_SECONDS, data.get(CONF_AUTOTUNE_SAMPLE_SECONDS, DEFAULT_AUTOTUNE_SAMPLE_SECONDS)))
        self.calibration_points_raw = str(options.get(CONF_CALIBRATION_POINTS, data.get(CONF_CALIBRATION_POINTS, DEFAULT_CALIBRATION_POINTS)))
        self.update_interval = int(options.get(CONF_UPDATE_INTERVAL, data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)))
        self.min_position = int(options.get(CONF_MIN_POSITION, data.get(CONF_MIN_POSITION, DEFAULT_MIN_POSITION)))
        self.max_position = int(options.get(CONF_MAX_POSITION, data.get(CONF_MAX_POSITION, DEFAULT_MAX_POSITION)))
        self.enable_temp_deadband = bool(options.get(CONF_ENABLE_TEMP_DEADBAND, data.get(CONF_ENABLE_TEMP_DEADBAND, DEFAULT_ENABLE_TEMP_DEADBAND)))
        self.temp_deadband = float(options.get(CONF_TEMP_DEADBAND, data.get(CONF_TEMP_DEADBAND, DEFAULT_TEMP_DEADBAND)))
        self.position_change_threshold = float(options.get(CONF_POSITION_CHANGE_THRESHOLD, data.get(CONF_POSITION_CHANGE_THRESHOLD, DEFAULT_POSITION_CHANGE_THRESHOLD)))
        self.cooling_delta_threshold = float(options.get(CONF_COOLING_DELTA_THRESHOLD, data.get(CONF_COOLING_DELTA_THRESHOLD, DEFAULT_COOLING_DELTA_THRESHOLD)))
        self.cooling_delta_hysteresis = float(options.get(CONF_COOLING_DELTA_HYSTERESIS, data.get(CONF_COOLING_DELTA_HYSTERESIS, DEFAULT_COOLING_DELTA_HYSTERESIS)))

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
        self._cooling_pid_allowed = False
        self._no_effect_count = 0
        self._autotune_active = False
        self._autotune_task = None
        self._calibration_points = self._parse_calibration_points(self.calibration_points_raw)
        self._calibration_max_cm = max((cm for _, cm in self._calibration_points), default=0.0)

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

    def _set_autotune_status(self, status: str) -> None:
        self.state.last_autotune_result = status
        self._notify()

    def _set_enabled_runtime(self, enabled: bool) -> None:
        self._enabled = enabled
        self.state.enabled = enabled
        self.state.status = "disabled" if not enabled else self.state.status
        self._notify()

    def _parse_calibration_points(self, raw: str) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for chunk in raw.replace("\n", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            sep = ":" if ":" in chunk else "=" if "=" in chunk else None
            if sep is None:
                continue
            left, right = chunk.split(sep, 1)
            try:
                command = float(left.strip())
                opening_cm = float(right.strip())
            except ValueError:
                continue
            points.append((command, opening_cm))
        points.sort(key=lambda item: item[0])
        return points

    def _refresh_calibration_points(self, raw: str) -> None:
        self.calibration_points_raw = raw
        self._calibration_points = self._parse_calibration_points(raw)
        self._calibration_max_cm = max((cm for _, cm in self._calibration_points), default=0.0)

    def _invert_calibration(self, desired_cm: float) -> float:
        if not self._calibration_points or self._calibration_max_cm <= 0:
            return desired_cm

        by_cm = sorted(self._calibration_points, key=lambda item: item[1])
        if desired_cm <= by_cm[0][1]:
            return by_cm[0][0]
        if desired_cm >= by_cm[-1][1]:
            return by_cm[-1][0]

        for idx in range(1, len(by_cm)):
            left_cmd, left_cm = by_cm[idx - 1]
            right_cmd, right_cm = by_cm[idx]
            if desired_cm <= right_cm:
                span = right_cm - left_cm
                if abs(span) < 1e-6:
                    return right_cmd
                ratio = (desired_cm - left_cm) / span
                return left_cmd + (right_cmd - left_cmd) * ratio
        return by_cm[-1][0]

    def _apply_calibration(self, desired_output: float) -> float:
        if not self._calibration_points or self._calibration_max_cm <= 0:
            return desired_output

        range_width = max(1.0, float(self.max_position - self.min_position))
        normalized = (desired_output - self.min_position) / range_width
        normalized = max(0.0, min(1.0, normalized))
        desired_cm = normalized * self._calibration_max_cm
        return self._invert_calibration(desired_cm)

    def _pid_gains(self) -> tuple[float, float, float]:
        return self.kp, self.ki, self.kd

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

        dt_hours = max(self.update_interval, 15) / 3600.0
        temperature_trend = None if self._last_temp is None or current_temp is None else (current_temp - self._last_temp) / dt_hours

        self.state.current_temp = current_temp
        self.state.outdoor_temp = outdoor_temp
        self.state.cooling_delta = cooling_delta
        self.state.cover_position = cover_position
        self.state.temperature_trend = temperature_trend
        self.state.enabled = self._enabled
        self.state.autotune_running = self._autotune_active

        if current_temp is None:
            self.state.status = "temp_sensor_unavailable"
            self.state.pid_output = float(self.min_position)
            if cover_available:
                await self._set_cover_position(float(self.min_position))
            self._notify()
            return

        if self._autotune_active:
            self.state.status = "idle"
            self._notify()
            return

        if not cover_available:
            self.state.status = "cover_unavailable"
            self._notify()
            return

        error = current_temp - self.target_temp
        self.state.error = error

        if not self._enabled or self.cooling_mode == COOLING_MODE_DISABLED:
            self._integral = 0.0
            self._previous_error = None
            self._last_temp = current_temp
            self.state.pid_output = float(self.min_position)
            self.state.status = "disabled"
            await self._set_cover_position(float(self.min_position))
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

        if self.enable_temp_deadband and current_temp < self.target_temp + self.temp_deadband:
            self._previous_error = error
            self._last_temp = current_temp
            self.state.status = "deadband"
            self._notify()
            return

        self._integral += error * dt_hours
        self._integral = max(-20.0, min(20.0, self._integral))
        derivative = 0.0 if self._previous_error is None else (error - self._previous_error) / dt_hours

        kp, ki, kd = self._pid_gains()
        output = kp * error + ki * self._integral + kd * derivative
        outdoor_temp_for_cooling = None if self.cooling_mode == COOLING_MODE_FORCE else outdoor_temp
        output *= self._adaptive_multiplier(outdoor_temp_for_cooling, temperature_trend)
        output = max(self.min_position, min(self.max_position, output))

        # If the temperature is not moving for several cycles, nudge the window open a bit more.
        temp_delta = None if self._last_temp is None else current_temp - self._last_temp
        if error > 0.0 and temp_delta is not None and abs(temp_delta) < 0.05:
            self._no_effect_count = min(self._no_effect_count + 1, 6)
        else:
            self._no_effect_count = 0

        if self._no_effect_count >= 2:
            output = min(self.max_position, output + min(20.0, self._no_effect_count * 5.0))

        self._previous_error = error
        self._last_temp = current_temp
        self._sample_count += 1
        self._last_update_tick = self.hass.loop.time()
        self._last_position = output
        self.state.pid_output = output
        self.state.status = "cooling"
        await self._set_cover_position(output)
        self._notify()

    async def _set_cover_position(self, position: float, apply_calibration: bool = True) -> None:
        if position < self.min_position:
            position = float(self.min_position)
        if position > self.max_position:
            position = float(self.max_position)

        if apply_calibration:
            position = self._apply_calibration(position)
            position = max(self.min_position, min(self.max_position, position))

        if self._last_sent_position is not None and abs(self._last_sent_position - position) < self.position_change_threshold:
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

    async def async_set_profile_mode(self, mode: str) -> None:
        await self.async_set_cooling_mode(mode)

    async def async_set_gain(self, key: str, value: float) -> None:
        setattr(self, key, value)
        self._async_save_option(key, value)
        self._notify()
        await self._async_tick(None)

    async def async_set_update_interval(self, value: int) -> None:
        self.update_interval = int(value)
        self._async_save_option(CONF_UPDATE_INTERVAL, self.update_interval)
        await self.async_stop()
        await self.async_start()

    async def async_set_autotune_sample_seconds(self, value: int) -> None:
        self.autotune_sample_seconds = int(value)
        self._async_save_option(CONF_AUTOTUNE_SAMPLE_SECONDS, self.autotune_sample_seconds)
        self._notify()

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

    async def async_set_temp_deadband_enabled(self, enabled: bool) -> None:
        self.enable_temp_deadband = bool(enabled)
        self._async_save_option(CONF_ENABLE_TEMP_DEADBAND, self.enable_temp_deadband)
        self._notify()
        await self._async_tick(None)

    async def async_set_temp_deadband(self, value: float) -> None:
        self.temp_deadband = float(value)
        self._async_save_option(CONF_TEMP_DEADBAND, self.temp_deadband)
        self._notify()
        await self._async_tick(None)

    async def async_set_position_change_threshold(self, value: float) -> None:
        self.position_change_threshold = float(value)
        self._async_save_option(CONF_POSITION_CHANGE_THRESHOLD, self.position_change_threshold)
        self._notify()
        await self._async_tick(None)

    async def async_set_calibration_points(self, value: str) -> None:
        raw = (value or "").strip()
        self._refresh_calibration_points(raw)
        self._async_save_option(CONF_CALIBRATION_POINTS, raw)
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
            self.state.status = "temp_sensor_unavailable"
            self.state.last_autotune_result = "autotune_no_temperature"
            self._notify()
            return

        current_position = self._cover_position()
        if current_position is None:
            current_position = float(self.min_position)

        self._autotune_active = True
        self._set_enabled_runtime(False)
        self._integral = 0.0
        self._previous_error = None
        self.state.autotune_running = True
        self._set_autotune_status("autotune_started")

        step_positions = [0.25, 0.5, 0.75, 1.0]
        total_range = max(1.0, float(self.max_position - self.min_position))
        targets = [round(self.min_position + total_range * fraction, 1) for fraction in step_positions]
        targets = [max(self.min_position, min(self.max_position, target)) for target in targets]
        if all(abs(target - current_position) < 1.0 for target in targets):
            self._set_autotune_status("autotune_finished_no_room")
            self._autotune_active = False
            self.state.autotune_running = False
            self._set_enabled_runtime(True)
            self._notify()
            return

        start_temp = current
        samples: list[float] = []
        sample_seconds = max(self.autotune_sample_seconds, self.update_interval * 4)
        sample_per_step = max(30, sample_seconds // max(1, len(targets)))
        start_monotonic = self.hass.loop.time()

        for idx, target_position in enumerate(targets, start=1):
            self._set_autotune_status(f"autotune_step_{idx}_move_{int(round(target_position))}")
            await self._set_cover_position(target_position)
            self._set_autotune_status(f"autotune_step_{idx}_sample")

            step_start = self.hass.loop.time()
            elapsed = 0.0
            while elapsed < sample_per_step:
                await asyncio.sleep(max(15, self.update_interval))
                now = self._read_float(self.temp_sensor)
                if now is not None:
                    samples.append(now)
                    self.state.current_temp = now
                    self._set_autotune_status(f"autotune_step_{idx}_sample_{len(samples)}")
                elapsed = self.hass.loop.time() - step_start

        self._set_autotune_status("autotune_step_3_calculating")
        end_temp = samples[-1] if samples else self._read_float(self.temp_sensor)
        if end_temp is None:
            end_temp = start_temp

        delta_pos = (targets[-1] - targets[0]) if len(targets) >= 2 else (targets[0] - current_position)
        delta_temp = end_temp - start_temp
        effect = abs(delta_temp) / max(abs(delta_pos), 1.0)
        intended = (current >= self.target_temp and delta_temp < 0) or (current < self.target_temp and delta_temp > 0)
        elapsed_hours = max((self.hass.loop.time() - start_monotonic) / 3600.0, 1 / 3600.0)

        if not intended or effect < 0.005:
            kp = max(self.kp, DEFAULT_KP)
            ki = max(self.ki, DEFAULT_KI)
            kd = max(self.kd, DEFAULT_KD)
            self._set_autotune_status("autotune_finished_noisy")
        else:
            kp = max(4.0, min(40.0, 1.5 / max(effect, 0.01)))
            ki = max(0.03, min(0.8, kp / max(elapsed_hours * 12.0, 8.0)))
            kd = max(0.0, min(3.0, kp * min(elapsed_hours, 0.5) / 3.0))
            self._set_autotune_status("autotune_finished")

        self.kp, self.ki, self.kd = kp, ki, kd
        self._async_save_option(CONF_KP, kp)
        self._async_save_option(CONF_KI, ki)
        self._async_save_option(CONF_KD, kd)

        await self._set_cover_position(current_position, apply_calibration=False)
        self._autotune_active = False
        self.state.autotune_running = False
        self._integral = 0.0
        self._previous_error = None
        self._set_enabled_runtime(True)
        self._notify()
        await self._async_tick(None)

    @property
    def available(self) -> bool:
        return self._enabled

    @property
    def sample_count(self) -> int:
        return self._sample_count
