---
title: "Hearth: Room Thermostat"
description: Instructions on how to connect Home Assistant's thermostat and room sensors to Hearth.
ha_release: 2026.12
ha_categories:
  - climate.thermostats_heating
ha_iot_class: Cloud Polling
ha_config_flow: true
ha_domain: hearth
ha_platforms:
  - diagnostics
  - sensor
ha_codeowners:
  - '@alexdlaird'
ha_integration_type: service
ha_quality_scale: platinum
---

The **Hearth** {% term integration %} connects Home Assistant to [Hearth](https://www.meethearth.app), a service and
app that runs a thermostat by the rooms people are in, not by the thermostat's own reading. Home Assistant sends Hearth
the thermostat and room temperature sensors it already has, and applies the setting Hearth answers with through Home
Assistant's own climate actions. Home Assistant only ever calls out to Hearth; nothing reaches into the home.

## Use cases

- Heat or cool to the bedroom at night and the living room in the evening, with a thermostat in the hallway.
- Use room sensors from any integration (Zigbee, Z-Wave, Matter, ESPHome, weather stations) as Hearth's rooms.
- Send only room sensors to a Hearth home whose thermostat Hearth reaches on its own (Daikin, Amana and Goodman).

## Prerequisites

- A Hearth home, set up in the Hearth app (iOS or Android). Demo homes can't be connected.
- The home's Hearth API key. In the Hearth app, setting up a home with Home Assistant shows it. For room sensors only,
  the home's admin creates it in **Settings** > **Manage home** > **Sensors** > **Other sensors (Hearth API)**.
- A `climate` entity for the thermostat, and room temperature sensors, already in Home Assistant.

{% include integrations/config_flow.md %}

{% configuration_basic %}
Hearth API key:
  description: "The key the Hearth home shows once. Making a new key in the Hearth app stops the old one."
Thermostat:
  description: "The thermostat Hearth runs. Leave it empty for a Daikin, Amana or Goodman thermostat, which Hearth reaches itself."
Room temperature sensors:
  description: "Up to 10. Humidity and battery sensors on the same device come along. Add each one to a room in the Hearth app."
{% endconfiguration_basic %}

## Configuration options

To change the thermostat or the room sensors later, use the integration's **Configure** button. To change the API
key, use **Reconfigure**. A key for a different Hearth home is refused; remove the integration and add the other home
instead.

## Data updates

The integration posts the thermostat and the room sensors to Hearth each minute, and soon after the thermostat changes
(at most once every 20 seconds). A sensor not reported for 30 minutes is left out of the post. When Hearth asks for
fewer posts, the integration waits as long as Hearth says.

## Supported devices

- Any thermostat Home Assistant has as a `climate` entity with a mode and target temperatures.
- Any sensor with the temperature device class, in °C or °F.

## Supported functionality

The integration adds a **Hearth** service device with two diagnostic sensors.

### Sensors

- **Bridge status**: what the bridge is doing, most urgent first:
  - **OK**: Hearth gets everything, and its last setting was applied.
  - **Slowed down by Hearth**: Hearth asked for fewer posts; posting resumes on its own.
  - **Hearth unreachable**: Home Assistant can't reach Hearth; it keeps trying each minute.
  - **Post refused by Hearth**: Hearth couldn't read a post.
  - **Thermostat missing** or **Thermostat unavailable**: the chosen thermostat isn't in Home Assistant, or isn't
    available.
  - **Setting not applied**: a setting from Hearth was outside the thermostat's limits, or the thermostat refused it.
  - **Sensors not added in Hearth**: some sensors are still waiting to be added to a room in the Hearth app.
- **Last sync**: when the bridge last reached Hearth with everything.

Hearth sets only the modes and setpoints the thermostat offers, within its limits and between 7 and 32 °C (45 and
90 °F). A mode change is sent on its own before the setpoints. A setting the thermostat refuses isn't tried again, and
a change someone makes at the thermostat stands.

## Examples

### Notify when the bridge needs attention

{% details "Example YAML configuration" %}

```yaml
alias: "Hearth bridge needs attention"
triggers:
  - trigger: state
    entity_id: sensor.hearth_bridge_status
    not_to:
      - ok
      - slowed_down
    for:
      minutes: 30
actions:
  - action: notify.notify
    data:
      message: "Hearth's bridge: {{ states('sensor.hearth_bridge_status') }}"
```

{% enddetails %}

## Known limitations

- Each Home Assistant connects one Hearth home, with up to 10 room sensors.
- Turn off the thermostat's own schedule, and anything else that changes its setpoints, in Home Assistant or the
  thermostat's app. Hearth doesn't turn them off through Home Assistant, and they would undo Hearth's settings.
- Hearth is a cloud service: without an internet connection, the thermostat keeps its last setting.

## Troubleshooting

{% details "Thermostat missing" %}

The thermostat chosen in **Configure** isn't in Home Assistant anymore (it was removed, or renamed). After 6 hours, a
repair is raised. Choose the thermostat again in the integration's **Configure**.

{% enddetails %}

{% details "Setting not applied" %}

Check the thermostat's modes and temperature limits in Home Assistant. The **Bridge status** sensor's `detail`
attribute says why the setting wasn't applied.

{% enddetails %}

{% details "Sensors not added in Hearth" %}

The **Bridge status** sensor's `sensors_not_added` attribute lists them. In the Hearth app, open **Settings** >
**Manage home** > **Sensors** and add each one to a room.

{% enddetails %}

## Removing the integration

This integration follows standard integration removal. No extra steps are required. Its sensors stay in Hearth until
they're removed in the Hearth app.

{% include integrations/remove_device_service.md %}
