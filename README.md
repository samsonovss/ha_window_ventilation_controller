# Window Ventilation Controller

Home Assistant custom integration for smart ventilation through a motorized window/cover.

The integration is designed for cooling and ventilation with outside air: it reads indoor temperature, optionally reads outdoor temperature, AC state, and CO₂, then moves a `cover` entity between 0–100% to keep the room near the target temperature and improve air quality.

## Features

- UI setup from Home Assistant Devices & services
- Indoor temperature sensor selection
- Controlled window/cover entity selection
- Optional outdoor temperature sensor for automatic cooling permission
- Optional AC climate entity selection with conflict protection
- Optional CO₂ sensor with ventilation assist
- Node-RED-style PID tuning: proportional band, integral time, derivative time
- Cooling modes: `disabled`, `force`, `auto`
- Cooling delta sensor: `current_temp - outdoor_temp`
- Cooling delta threshold with hysteresis
- Temperature deadband to avoid unnecessary movement near target
- Position change threshold to avoid tiny cover updates
- Controller status sensor for debugging/automation
- CO₂ status sensor for ventilation diagnostics

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
- common PID tuning values are used
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


## PID behavior

The PID calculation follows the same style as `node-red-contrib-pid`:

- `Proportional band` is the temperature range that maps the output from 0% to 100%.
- `Integral time` is in seconds. A larger value makes the integral correction slower.
- `Derivative time` is in seconds. Set it to `0` to disable derivative action.
- For cooling, the Node-RED output is inverted, so a room temperature above target opens the window more.
- There is no extra boost or adaptive multiplier; the cover position comes only from PID output and min/max limits.

## Temperature deadband

Default: `0.5 °C`

Set it to `0 °C` to disable deadband.

Logic:

- `current_temp <= target_temp` → window moves to `Minimum cover position`
- `target_temp < current_temp < target_temp + deadband` → window is not moved and PID integral is not accumulated
- `current_temp >= target_temp + deadband` → PID runs normally
- `deadband = 0` → this guard is disabled

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
- `ac_active_window_closed` — AC protection is active and the window is forced closed
- `outdoor_sensor_unavailable` — outdoor sensor is unavailable in auto mode
- `temp_sensor_unavailable` — indoor temperature sensor is unavailable
- `cover_unavailable` — controlled cover entity is unavailable
- `idle` — no cooling action is currently required
- `integral_locked` — PID output is limited and integral accumulation is temporarily held to avoid wind-up
- `error` — unexpected controller update error

## Settings / entities

Home Assistant still exposes tunable values as `number` entities, but they are rendered as sliders where possible.

Main controls:

- `Cooling mode` (`disabled` / `force` / `auto`)
- `AC conflict protection` switch, shown only when a climate entity is selected
- `Target temperature`
- `Temperature error`
- `Room`
- `Outdoor temperature`
- `Window position`
- `Controller status`

Configuration:

- `AC climate entity` — optional; if selected, AC conflict protection becomes available
- `PID profile` — applies PID tuning presets:
  - `soft`: proportional band `10 °C`, integral time `5400 s`, derivative time `0 s`, position change threshold `2%`
  - `normal`: proportional band `6 °C`, integral time `3600 s`, derivative time `0 s`, position change threshold `1%`
  - `aggressive`: proportional band `4 °C`, integral time `1800 s`, derivative time `0 s`, position change threshold `0.5%`
  - `manual`: shown when PID tuning values are changed directly
- `Temperature deadband` — default `0.5 °C`, range `0–2 °C`, step `0.1 °C`; set `0` to disable
- `Proportional band` — default `6 °C`; Node-RED-style proportional band in °C; smaller means more aggressive
- `Integral time` — Node-RED-style integral time in seconds; larger means slower integral action
- `Derivative time` — Node-RED-style derivative time in seconds; `0` disables derivative action
- `Cooling delta threshold` — default `3 °C`, range `3–20 °C`, step `0.5 °C`
- `Cooling delta hysteresis` — default `1 °C`, range `0–5 °C`, step `0.5 °C`
- `Position change threshold` — default `1%`, range `0–10%`, step `0.5%`
- `Update interval`

Diagnostic sensors:

- `Cooling delta`
- `PID output`

Removed legacy/debug entities:

- `PID Window Enabled` switch
- `Temp sensor guard` switch
- `Enable temperature deadband` switch
- `Temperature trend` sensor

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install **Window Ventilation Controller**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Select the room sensor, optional outdoor sensor, and target window/door cover.

### Manual installation

Copy `custom_components/pid_window` to `/config/custom_components/pid_window` and restart Home Assistant.

## Languages

The integration includes English and Russian translations for config flow, options flow, entity names, select options, and status values.

Translation files are stored in `custom_components/pid_window/translations/en.json` and `custom_components/pid_window/translations/ru.json`, as expected by Home Assistant custom integrations.

## Notes

- The controlled window/cover must support 0–100% positioning.
- `force` mode can work without an outdoor sensor.
- `auto` mode requires an outdoor sensor; if it is unavailable, PID is blocked safely.
- The integration is focused on cooling by opening a window when outside air is colder than room air.
