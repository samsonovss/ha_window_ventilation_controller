# Ventilation Controller

[Русская версия](README.ru.md)

<p align="center">
  <img src="assets/dashboard-banner.png" alt="Ventilation Controller dashboard" width="100%">
</p>

Ventilation Controller is a Home Assistant custom integration for rooms with a motorized window, door, damper, or any other `cover` entity that can be positioned from 0 to 100%.

It works well for Drivent window actuators, but it is not tied to Drivent. Any Home Assistant `cover` entity with 0-100% position control can be used.

The idea is simple: the integration opens the window only when it is useful.

It watches the room temperature, optional outdoor temperature, target temperature, optional AC state, optional CO₂ level, and optional exhaust fan. If outdoor air can actually cool the room, the controller can open the window. If the outdoor air is not useful, it keeps the window closed. If the AC is running, it can close the window so you do not cool the street. If CO₂ gets high, it can add a ventilation minimum without fighting the temperature PID. If the window is already open but natural airflow is not enough, it can use an exhaust fan or switch as a booster.

In plain English: this is smart ventilation for Home Assistant. The window opens when it helps, stays closed when it does not, and an optional exhaust fan can help move air when the open window alone is not enough. The integration still exposes enough diagnostics to understand why it did what it did.

## Contents

- [What It Can Do](#what-it-can-do)
- [How It Works](#how-it-works)
- [Temperature Ventilation](#temperature-ventilation)
- [CO₂ Ventilation Assist](#co₂-ventilation-assist)
- [Exhaust Fan Assist](#exhaust-fan-assist)
- [PID Behavior](#pid-behavior)
- [Controller Status](#controller-status)
- [Settings And Entities](#settings-and-entities)
- [Installation](#installation)
- [Notes](#notes)
- [Authors](#authors)
- [Support / Поддержать](#support--поддержать)

## What It Can Do

- Control a motorized window, door, damper, or vent through a Home Assistant `cover` entity
- Compatible with Drivent actuators and other 0-100% positionable covers
- Use indoor temperature and a target temperature to calculate the window position
- Use optional outdoor temperature to decide whether cooling with outside air makes sense
- Support temperature ventilation modes: `disabled`, `force`, and `auto`
- Avoid opening the window when outdoor air is not useful
- Use a temperature deadband so the window does not twitch around the target
- Protect against AC conflicts by closing the window when a selected climate entity is cooling
- Use optional CO₂ ventilation assist for air quality
- Treat CO₂ as part of the same final window-position calculation, not as a separate automation
- Use an optional exhaust fan or switch as an airflow booster when the window is already open
- Show status sensors for temperature control, CO₂ ventilation, and fan assist
- Expose tuning values as Home Assistant entities

## How It Works

The integration controls one `cover` entity. The cover must support percentage positioning.

For temperature control, it calculates a PID output between your configured minimum and maximum window position. In `auto` mode, it first checks whether the room is warmer than outdoors by enough degrees. If not, the PID is blocked because opening the window would not help.

For CO₂ control, the integration can apply a temporary minimum window position. Example:

- PID wants `10%`
- CO₂ ventilation wants at least `30%`
- final window position becomes `max(10, 30) = 30%`

If PID already wants `100%`, CO₂ does not override anything. It simply reports that CO₂ ventilation is active while the main temperature controller remains in charge.

An optional exhaust fan can be selected as a `fan` or `switch` entity. It does not replace the window PID. It only helps airflow after the window is already open enough and natural ventilation is not producing enough effect.

## Temperature Ventilation

### `disabled`

The controller is disabled.

- PID does not run
- window is moved to the minimum position
- controller status is `disabled`

### `force`

PID runs using indoor temperature only.

- outdoor temperature is not required
- cooling delta is not used to block PID
- controller status is `cooling` while PID is regulating

### `auto`

PID runs only when outside air can cool the room.

- outdoor temperature sensor is required
- `Cooling delta = current_temp - outdoor_temp`
- PID is allowed when `Cooling delta >= Cooling delta threshold`
- PID is blocked when `Cooling delta <= threshold - hysteresis`
- between those values, the previous allowed/blocked state is kept

If the outdoor sensor is unavailable in `auto` mode, PID is blocked and the window is moved to the minimum position.

## CO₂ Ventilation Assist

CO₂ support is optional. If no CO₂ sensor is selected, CO₂ entities and logic are not created.

When a CO₂ sensor is selected, the integration can expose:

- `CO₂` sensor
- `CO₂ status`
- `CO₂ ventilation` mode: `disabled` or `auto`
- CO₂ threshold and hysteresis
- CO₂ ventilation position
- CO₂ no-effect detection
- cold outdoor-air guard settings

CO₂ does not send separate commands to the window. It only contributes a minimum position to the same final calculation used by PID.

CO₂ ventilation is blocked when:

- temperature ventilation is disabled
- AC conflict protection is active and the AC is cooling
- `auto` mode says outdoor air is not useful
- the room is already near or below the target temperature

## Exhaust Fan Assist

Exhaust fan support is optional. If no fan or switch entity is selected, fan entities and logic are not created.

The fan mode has two states:

- `disabled` — the integration never touches the fan
- `auto` — the integration can turn the fan on or off when airflow needs help

In `auto`, the fan can turn on for temperature only when:

- the window is already open at or above `Fan minimum window position`
- the room is above target plus the temperature deadband
- outdoor air is cooler by at least the configured cooling delta threshold
- AC conflict protection is not blocking ventilation
- the room temperature has not dropped enough during `Fan no cooling timeout`

For CO₂, the fan can turn on when CO₂ ventilation is active and the window is already open at or above the fan minimum window position.

Manual fan control has priority in `auto`: if you turn the fan entity on or off manually, the integration holds that manual state for `Fan manual override timeout` before auto control resumes.

The same physical fan can be selected in several Ventilation Controller entries. Fan requests are shared by entity ID: the fan is turned on when at least one room requests airflow boost, and it is turned off only when no room requests it anymore. If the fan is selected in only one entry, behavior is the same as a single local fan.

## PID Behavior

The PID calculation follows the same style as `node-red-contrib-pid`:

- `PID proportional band` is the temperature range that maps output from 0% to 100%
- `PID integral time` is in seconds; larger values make integral correction slower
- `PID derivative time` is in seconds; `0` disables derivative action
- for cooling, the Node-RED output is inverted, so a room temperature above target opens the window more

## Controller Status

The main controller status explains the temperature/window decision:

- `disabled` — temperature ventilation is disabled
- `cooling` — PID is active and regulating the window
- `deadband` — room temperature is inside the deadband
- `auto_blocked_by_delta` — outdoor air is not useful enough
- `ac_active_window_closed` — AC protection closed the window
- `outdoor_sensor_unavailable` — outdoor sensor is unavailable in auto mode
- `temp_sensor_unavailable` — indoor temperature sensor is unavailable
- `cover_unavailable` — controlled cover entity is unavailable
- `idle` — no cooling action is needed
- `integral_locked` — PID output is at a limit and integral accumulation is temporarily held
- `co2_ventilating` — CO₂ raised the final window position above PID
- `co2_no_effect` — CO₂ ventilation did not reduce CO₂ enough within the configured timeout
- `error` — unexpected controller update error

The CO₂ status separately explains the CO₂ side:

- `disabled`
- `idle`
- `co2_high`
- `co2_ventilating`
- `co2_blocked_by_delta`
- `co2_blocked_by_ac`
- `co2_blocked_by_temperature`
- `co2_no_effect`

The fan status explains the exhaust fan side:

- `disabled`
- `idle`
- `auto_waiting`
- `temperature_boost`
- `co2_boost`
- `manual_on`
- `manual_off`
- `cooldown`
- `blocked_by_ac`
- `blocked_by_window`
- `max_runtime`

## Settings And Entities

Main controls:

- `Temperature ventilation`: `disabled`, `force`, `auto`
- `CO₂ ventilation`: `disabled`, `auto`, shown only when a CO₂ sensor is selected
- `Fan mode`: `disabled`, `auto`, shown only when a fan or switch entity is selected
- `AC conflict protection`, shown only when an AC climate entity is selected
- `Target temperature`
- `Room`
- `Outdoor temperature`
- `Window position`
- `Controller status`

Configuration and tuning:

- `Ventilation PID profile`
- `PID proportional band`
- `PID integral time`
- `PID derivative time`
- `Temperature deadband`
- `Outdoor cooling delta threshold`
- `Outdoor cooling delta hysteresis`
- `Window movement threshold`
- `System update interval`
- CO₂ threshold, hysteresis, ventilation position, timeout, minimum drop, and cold-air guards
- fan minimum window position, no-cooling timeout, minimum temperature drop, max runtime, cooldown, and manual override timeout

Diagnostic sensors:

- `Cooling delta`
- `PID output`
- `CO₂ position`
- `Fan status`

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install **Ventilation Controller**.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & services -> Add integration**.
6. Select the room sensor, optional outdoor sensor, optional AC entity, optional CO₂ sensor, optional fan/switch entity, and target cover.

### Manual Installation

Copy `custom_components/ventilation_controller` to `/config/custom_components/ventilation_controller` and restart Home Assistant.

## Notes

- The controlled cover must support 0-100% positioning.
- `force` mode can work without an outdoor sensor.
- `auto` mode requires an outdoor sensor.
- AC protection never turns the AC on or off; it only reacts to the selected climate entity state.
- CO₂ ventilation never controls the window separately; it only participates in the final position calculation.
- Fan assist never changes the PID output or window target; it only turns the selected fan/switch on or off.
- The same fan/switch may be reused by several rooms; requests are coordinated so one room does not turn the fan off while another room still needs it.

## Authors

Created by [@samsonovss](https://github.com/samsonovss) with help from Shade, an OpenClaw personal AI agent.

## Support / Поддержать

If this integration is useful to you, you can support its development:

- PayPal: samsonov@hotmail.com
- Telegram: https://t.me/samsonovss
- Bitcoin (BTC): `bc1q3cza0kasutzes4hfddxuclmd9ghn5v7zw2nr5c`

Please send **Bitcoin (BTC) only** to the address above. Do not send USDT, ETH, BNB, TRX, or other tokens to this address.

Thank you for supporting the integration.

Если эта интеграция полезна, можно поддержать её разработку:

- PayPal: samsonov@hotmail.com
- Telegram: https://t.me/samsonovss
- Bitcoin (BTC): `bc1q3cza0kasutzes4hfddxuclmd9ghn5v7zw2nr5c`

Пожалуйста, отправляйте на этот адрес **только Bitcoin (BTC)**. Не отправляйте USDT, ETH, BNB, TRX или другие токены на этот адрес.

Спасибо за поддержку интеграции.
