# PID Window Controller

Home Assistant custom integration for controlling a motorized window/cover with PID.

The integration is designed for cooling a room with outside air: it reads indoor temperature, optionally reads outdoor temperature, and moves a `cover` entity between 0–100% to keep the room near the target temperature.

## Features

- UI setup from Home Assistant Devices & services
- Indoor temperature sensor selection
- Controlled window/cover entity selection
- Optional outdoor temperature sensor for automatic cooling permission
- One common PID tuning set: `PID Kp`, `PID Ki`, `PID Kd`
- Cooling modes: `disabled`, `force`, `auto`
- Cooling delta sensor: `current_temp - outdoor_temp`
- Cooling delta threshold with hysteresis
- Temperature deadband to avoid unnecessary movement near target
- Position change threshold to avoid tiny cover updates
- Controller status sensor for debugging/automation
- Optional actuator calibration curve
- Autotune button with a real stepped window test

## Cooling modes

### `disabled`

The controller is disabled.

- PID does not run
- window is moved to `Minimum cover position`
- `Controller status = disabled`

### `force`

PID runs using indoor temperature only.

- outdoor temperature is not required
- cooling delta is not used to block PID
- common `PID Kp / Ki / Kd` values are used
- `Controller status = cooling` while PID is regulating

### `auto`

PID runs only when outside air can cool the room.

- outdoor temperature sensor is required
- `Cooling delta = current_temp - outdoor_temp`
- PID is allowed when `Cooling delta >= Cooling delta threshold`
- PID is blocked when `Cooling delta <= threshold - hysteresis`
- between those two values, the previous allowed/blocked state is kept

If the outdoor sensor is unavailable in `auto` mode:

- `Cooling delta` becomes unavailable
- PID is blocked
- window is moved to `Minimum cover position`
- `Controller status = outdoor_sensor_unavailable`

## Temperature deadband

Temperature deadband is enabled by default.

Default: `0.5 °C`

Logic:

- `current_temp <= target_temp` → window moves to `Minimum cover position`
- `target_temp < current_temp < target_temp + deadband` → window is not moved and PID integral is not accumulated
- `current_temp >= target_temp + deadband` → PID runs normally

This prevents the window from constantly moving around the target temperature.

## Position change threshold

Default: `1%`

The integration sends `cover.set_cover_position` only when the new calculated position differs from the last sent position by at least the configured threshold.

This prevents noisy PID output from spamming tiny 1% cover movements.

## Controller status

The `Controller status` sensor shows the current controller state.

Possible values:

- `disabled` — cooling mode is disabled, window is kept at minimum position
- `cooling` — PID is active and regulating the window
- `deadband` — temperature is inside the deadband, window is not moved
- `auto_blocked_by_delta` — auto mode is active, but cooling delta is below the allowed threshold
- `outdoor_sensor_unavailable` — outdoor sensor is unavailable in auto mode
- `temp_sensor_unavailable` — indoor temperature sensor is unavailable
- `cover_unavailable` — controlled cover entity is unavailable
- `idle` — no cooling action is currently required
- `error` — unexpected controller update error

## Settings / entities

Home Assistant still exposes tunable values as `number` entities, but they are rendered as sliders where possible.

Main controls:

- `Cooling mode` (`disabled` / `force` / `auto`)
- `Target temperature`
- `Enable temperature deadband`
- `Temperature deadband` — default `0.5 °C`, range `0–2 °C`, step `0.1 °C`
- `Autotune` button

Configuration:

- `PID Kp`
- `PID Ki`
- `PID Kd`
- `Cooling delta threshold` — default `8 °C`, range `3–20 °C`, step `0.5 °C`
- `Cooling delta hysteresis` — default `1 °C`, range `0–5 °C`, step `0.5 °C`
- `Position change threshold` — default `1%`, range `0–10%`, step `0.5%`
- `Adaptive outdoor factor`
- `Adaptive rate factor`
- `Update interval`
- `Autotune sample seconds`
- `Calibration points`

Sensors:

- `Controller status`
- `Cooling delta`
- `Indoor temperature`
- `Outdoor temperature`
- `Window position`
- `PID output`

Removed legacy/debug entities:

- `PID Window Enabled` switch
- `Temp sensor guard` switch
- `Temperature error` sensor
- `Temperature trend` sensor

## Migration from old PID profiles

Older versions had separate PID profiles:

- `Winter Kp / Ki / Kd`
- `Summer Kp / Ki / Kd`
- `PID Profile Mode`

These are removed.

On update, the integration migrates old config entries:

- old `winter_kp / winter_ki / winter_kd` become the new common `PID Kp / PID Ki / PID Kd`
- if winter values are missing, defaults are used
- old summer values are ignored
- deprecated winter/summer and old debug/control entities are removed from the entity registry

After update, only the common PID settings should remain visible.

## Calibration points

Optional text field with points in the form:

```text
10:0.5,20:1.0,30:1.5,50:2.5,100:12.0
```

This maps PID output percent to the real opening of the window/actuator.

## Autotune

Autotune temporarily disables normal PID, moves the window through stepped positions, samples the room response, updates the common PID coefficients, then restores normal control.

It is a real stepped response test, not an instant coefficient guess.

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install **PID Window Controller**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Select the indoor temperature sensor and the target cover.
7. Optional: select the outdoor temperature sensor if you want to use `auto` cooling mode.

### Manual installation

Copy `custom_components/pid_window` to `/config/custom_components/pid_window` and restart Home Assistant.

## Notes

- The controlled window/cover must support 0–100% positioning.
- `force` mode can work without an outdoor sensor.
- `auto` mode requires an outdoor sensor; if it is unavailable, PID is blocked safely.
- The integration is focused on cooling by opening a window when outside air is colder than room air.
